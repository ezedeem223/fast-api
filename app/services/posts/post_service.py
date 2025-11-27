"""Service layer for post operations."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import datetime
from io import BytesIO
from http import HTTPStatus
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.celery_worker import schedule_post_publication
from app.content_filter import check_content, filter_content
from app.modules.community import Community, CommunityMember
from app.modules.utils.content import (
    get_or_create_hashtag,
    is_content_offensive,
    process_mentions,
    send_repost_notification,
    update_repost_statistics,
)
from app.modules.utils.events import log_user_event
from app.notifications import create_notification
from app.services.reporting import submit_report
from app.core.database.query_helpers import (
    optimize_post_query,
    paginate_query,
)


def _create_pdf(post: models.Post):
    """
    Generates a PDF file from a post's content.
    Returns a BytesIO object containing the PDF data if successful.
    """
    from xhtml2pdf import pisa  # Local import keeps dependency optional during tests.

    html = f"""
    <html>
    <head>
        <title>{post.title}</title>
    </head>
    <body>
        <h1>{post.title}</h1>
        <p>Posted by: {getattr(post.owner, 'username', post.owner.email)}</p>
        <p>Date: {post.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <div>
            {post.content}
        </div>
    </body>
    </html>
    """
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        return BytesIO(result.getvalue())
    return None


HTTP_422_UNPROCESSABLE_CONTENT = getattr(
    status, "HTTP_422_UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY
)

logger = logging.getLogger(__name__)


class PostService:
    def __init__(self, db: Session):
        self.db = db

    def _prepare_post_response(
        self, post: models.Post, owner: Optional[models.User] = None
    ) -> schemas.PostOut:
        """Ensure ORM posts expose the virtual fields expected by schemas."""
        owner = owner or getattr(post, "owner", None)
        default_privacy = getattr(owner, "privacy_level", schemas.PrivacyLevel.PUBLIC)
        if (
            not hasattr(post, "privacy_level")
            or getattr(post, "privacy_level", None) is None
        ):
            setattr(post, "privacy_level", default_privacy)
        if not hasattr(post, "poll_data"):
            setattr(post, "poll_data", None)
        return schemas.PostOut.model_validate(post, from_attributes=True)

    def _prepare_post_list(self, posts: List[models.Post]) -> List[schemas.PostOut]:
        return [self._prepare_post_response(post) for post in posts]

    def create_post(
        self,
        *,
        background_tasks: BackgroundTasks,
        payload: schemas.PostCreate,
        current_user: models.User,
        queue_email_fn: Callable,
        schedule_email_fn: Callable,
        broadcast_fn: Callable,
        share_on_twitter_fn: Callable[[str], None],
        share_on_facebook_fn: Callable[[str], None],
        mention_notifier_fn: Callable,
        analyze_content_fn: Callable[[str], dict] | None = None,
    ) -> models.Post:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not verified.",
            )

        if not payload.content.strip():
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Content cannot be empty",
            )

        warnings, bans = check_content(self.db, payload.content)
        if bans:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Content contains banned words: {', '.join(bans)}",
            )
        if warnings:
            logger.warning("Content contains warned words: %s", ", ".join(warnings))

        filtered_content = filter_content(self.db, payload.content)
        clean_title = payload.title.strip()
        post_language = getattr(current_user, "preferred_language", "en") or "en"

        if payload.community_id:
            community = (
                self.db.query(Community)
                .filter(Community.id == payload.community_id)
                .first()
            )
            if not community:
                raise HTTPException(status_code=404, detail="Community not found")
            # Basic rule enforcement hook; reuse content filter for now
            rule_warnings, _ = check_content(self.db, filtered_content)
            if rule_warnings:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Post content violates community rules",
                )

        new_post = models.Post(
            owner_id=current_user.id,
            title=clean_title,
            content=filtered_content,
            is_safe_content=True,
            community_id=payload.community_id,
            is_help_request=payload.is_help_request,
            language=post_language,
            category_id=payload.category_id,
            scheduled_time=payload.scheduled_time,
            is_published=payload.scheduled_time is None,
            copyright_type=payload.copyright_type,
            custom_copyright=payload.custom_copyright,
        )

        for hashtag_name in payload.hashtags:
            hashtag = get_or_create_hashtag(self.db, hashtag_name)
            new_post.hashtags.append(hashtag)

        mentioned_users = process_mentions(payload.content, self.db)
        new_post.mentioned_users = mentioned_users

        analyze_requested = getattr(payload, "analyze_content", False)
        if analyze_requested:
            if analyze_content_fn is None:
                raise HTTPException(
                    status_code=500, detail="Content analysis service is unavailable"
                )
            analysis_result = analyze_content_fn(payload.content)
            new_post.sentiment = analysis_result["sentiment"]["sentiment"]
            new_post.sentiment_score = analysis_result["sentiment"]["score"]
            new_post.content_suggestion = analysis_result["suggestion"]

        is_offensive, confidence = is_content_offensive(new_post.content)
        if is_offensive:
            new_post.is_flagged = True
            new_post.flag_reason = f"AI detected potentially offensive content (confidence: {confidence:.2f})"

        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)

        log_user_event(
            self.db, current_user.id, "create_post", {"post_id": new_post.id}
        )

        queue_email_fn(
            background_tasks,
            to=current_user.email,
            subject="New Post Created",
            body=f"Your post '{clean_title}' has been created successfully.",
        )
        schedule_email_fn(
            background_tasks,
            to=current_user.email,
            subject="New Post Created",
            body=f"Your post '{clean_title}' has been created successfully.",
        )

        broadcast_message = f"New post created: {new_post.title}"
        try:
            result = broadcast_fn(broadcast_message)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Broadcast failed for post %s: %s", new_post.id, exc)
        else:
            if inspect.isawaitable(result):
                background_tasks.add_task(asyncio.run, result)

        try:
            share_on_twitter_fn(new_post.content)
            share_on_facebook_fn(new_post.content)
        except HTTPException as exc:
            logger.error("Error sharing on social media: %s", exc.detail)

        if payload.scheduled_time:
            schedule_post_publication.apply_async(
                args=[new_post.id], eta=payload.scheduled_time
            )

        for user in mentioned_users:
            background_tasks.add_task(
                mention_notifier_fn,
                user.email,
                current_user.username,
                new_post.id,
            )

        return self._prepare_post_response(new_post, current_user)

    async def get_post(
        self,
        *,
        post_id: int,
        current_user: models.User,
        translator_fn,
    ) -> schemas.PostOut:
        post_query = (
            self.db.query(models.Post)
            .options(
                joinedload(models.Post.comments).joinedload(models.Comment.replies),
                joinedload(models.Post.reactions),
                joinedload(models.Post.mentioned_users),
                joinedload(models.Post.poll_options),
                joinedload(models.Post.poll),
            )
            .filter(models.Post.id == post_id)
        )

        post = post_query.first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {post_id} was not found",
            )

        reaction_counts = (
            self.db.query(
                models.Reaction.reaction_type,
                func.count(models.Reaction.id).label("count"),
            )
            .filter(models.Reaction.post_id == post_id)
            .group_by(models.Reaction.reaction_type)
            .all()
        )

        comments = []
        comments_dict: dict[int, dict] = {}
        for comment in post.comments:
            comment_data = comment.__dict__.copy()
            comment_data["replies"] = []
            comment_data["reactions"] = [
                schemas.Reaction(
                    id=r.id, user_id=r.user_id, reaction_type=r.reaction_type
                )
                for r in comment.reactions
            ]
            comment_data["reaction_counts"] = self._get_comment_reaction_counts(
                comment.id
            )
            comments_dict[comment.id] = comment_data
            if comment.parent_id is None:
                comments.append(comment_data)
            else:
                parent = comments_dict.get(comment.parent_id)
                if parent:
                    parent["replies"].append(comment_data)

        poll_data = None
        if post.is_poll:
            poll_options = [
                schemas.PollOption(id=option.id, option_text=option.option_text)
                for option in post.poll_options
            ]
            poll_data = schemas.PollData(
                options=poll_options,
                end_date=post.poll[0].end_date if post.poll else None,
            )

        post_out = schemas.PostOut(
            id=post.id,
            title=post.title,
            content=post.content,
            created_at=post.created_at,
            owner_id=post.owner_id,
            owner=post.owner,
            reactions=[
                schemas.Reaction(
                    id=r.id, user_id=r.user_id, reaction_type=r.reaction_type
                )
                for r in post.reactions
            ],
            reaction_counts=[
                schemas.ReactionCount(reaction_type=r.reaction_type, count=r.count)
                for r in reaction_counts
            ],
            community_id=post.community_id,
            comments=comments,
            mentioned_users=[
                schemas.UserOut.model_validate(user) for user in post.mentioned_users
            ],
            sentiment=post.sentiment,
            sentiment_score=post.sentiment_score,
            content_suggestion=post.content_suggestion,
            is_audio_post=post.is_audio_post,
            audio_url=post.audio_url if post.is_audio_post else None,
            is_poll=post.is_poll,
            poll_data=poll_data,
        )

        post_out.content = await translator_fn(
            post.content, current_user, post.language
        )
        post_out.title = await translator_fn(post.title, current_user, post.language)
        return post_out

    def search_posts(
        self, *, search: schemas.PostSearch, current_user: models.User
    ) -> list[schemas.PostOut]:
        query = self.db.query(models.Post)
        if search.keyword:
            query = query.filter(
                models.Post.title.contains(search.keyword)
                | models.Post.content.contains(search.keyword)
            )
        if search.category_id:
            query = query.filter(models.Post.category_id == search.category_id)
        if search.hashtag:
            query = query.join(models.Post.hashtags).filter(
                models.Hashtag.name == search.hashtag
            )
        posts = query.all()
        return [schemas.PostOut.model_validate(post) for post in posts]

    def get_scheduled_posts(
        self, *, current_user: models.User
    ) -> List[schemas.PostOut]:
        scheduled_posts = (
            self.db.query(models.Post)
            .filter(
                models.Post.owner_id == current_user.id,
                models.Post.scheduled_time.isnot(None),
                models.Post.is_published.is_(False),
            )
            .all()
        )
        return [schemas.PostOut.model_validate(post) for post in scheduled_posts]

    def upload_file_post(
        self,
        *,
        file: UploadFile,
        current_user: models.User,
        media_dir: Path,
    ) -> schemas.PostOut:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not verified.",
            )

        media_dir.mkdir(parents=True, exist_ok=True)
        file_location = media_dir / file.filename

        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())

        new_post = models.Post(
            owner_id=current_user.id,
            title=file.filename,
            content=str(file_location),
            is_safe_content=True,
        )
        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)
        return self._prepare_post_response(new_post, current_user)

    def delete_post(self, *, post_id: int, current_user: models.User) -> None:
        post_query = self.db.query(models.Post).filter(models.Post.id == post_id)
        post = post_query.first()
        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {post_id} does not exist",
            )
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to perform requested action",
            )
        post_query.delete(synchronize_session=False)
        self.db.commit()
        log_user_event(self.db, current_user.id, "delete_post", {"post_id": post_id})

    def update_post(
        self,
        *,
        post_id: int,
        payload: schemas.PostCreate,
        current_user: models.User,
        analyze_content_fn: Callable[[str], dict] | None = None,
    ) -> models.Post:
        post_query = self.db.query(models.Post).filter(models.Post.id == post_id)
        post = post_query.first()
        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {post_id} does not exist",
            )
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to perform requested action",
            )
        if not payload.content.strip():
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Content cannot be empty",
            )

        if payload.copyright_type is not None:
            post.copyright_type = payload.copyright_type
        if payload.custom_copyright is not None:
            post.custom_copyright = payload.custom_copyright

        new_mentions = process_mentions(payload.content, self.db)
        post.mentioned_users = new_mentions
        post.title = payload.title
        post.content = payload.content
        post.category_id = payload.category_id
        post.is_help_request = payload.is_help_request

        followers = (
            self.db.query(models.Follow)
            .filter(models.Follow.followed_id == current_user.id)
            .all()
        )
        for follower in followers:
            username = getattr(current_user, "username", current_user.email)
            create_notification(
                self.db,
                follower.follower_id,
                f"{username} updated a post",
                f"/post/{post.id}",
                "post_update",
                post.id,
            )

        analyze_requested = getattr(payload, "analyze_content", False)
        if analyze_requested:
            if analyze_content_fn is None:
                raise HTTPException(
                    status_code=500, detail="Content analysis service is unavailable"
                )
            analysis_result = analyze_content_fn(payload.content)
            post.sentiment = analysis_result["sentiment"]["sentiment"]
            post.sentiment_score = analysis_result["sentiment"]["score"]
            post.content_suggestion = analysis_result["suggestion"]

        self.db.commit()
        self.db.refresh(post)
        return post

    def create_short_video(
        self,
        *,
        background_tasks: BackgroundTasks,
        file: UploadFile,
        current_user: models.User,
        media_dir: Path,
        queue_email_fn: Callable,
    ) -> models.Post:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not verified.",
            )

        media_dir.mkdir(parents=True, exist_ok=True)
        file_location = media_dir / file.filename
        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())

        new_post = models.Post(
            owner_id=current_user.id,
            title=file.filename,
            content=str(file_location),
            is_safe_content=True,
            is_short_video=True,
        )
        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)

        queue_email_fn(
            background_tasks,
            to=current_user.email,
            subject="New Short Video Created",
            body=f"Your short video '{new_post.title}' has been created successfully.",
        )
        return self._prepare_post_response(new_post, current_user)

    def get_recommendations(
        self,
        *,
        current_user: models.User,
        limit_followed: int = 10,
        limit_others: int = 5,
    ) -> List[schemas.Post]:
        followed_users = (
            self.db.query(models.Follow.followed_id)
            .filter(models.Follow.follower_id == current_user.id)
            .subquery()
        )
        recommended_posts = (
            self.db.query(models.Post)
            .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
            .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
            .filter(models.Post.owner_id.in_(followed_users))
            .group_by(models.Post.id)
            .order_by(
                func.count(models.Vote.id).desc(),
                func.count(models.Comment.id).desc(),
                models.Post.created_at.desc(),
            )
            .limit(limit_followed)
            .all()
        )

        other_posts = (
            self.db.query(models.Post)
            .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
            .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
            .filter(
                ~models.Post.owner_id.in_(followed_users),
                models.Post.owner_id != current_user.id,
            )
            .group_by(models.Post.id)
            .order_by(
                func.count(models.Vote.id).desc(),
                func.count(models.Comment.id).desc(),
                models.Post.created_at.desc(),
            )
            .limit(limit_others)
            .all()
        )

        return recommended_posts + other_posts

    def list_post_comments(
        self,
        *,
        post_id: int,
        skip: int,
        limit: int,
    ) -> List[models.Comment]:
        return (
            self.db.query(models.Comment)
            .filter(models.Comment.post_id == post_id)
            .order_by(
                models.Comment.is_pinned.desc(),
                models.Comment.pinned_at.desc().nullslast(),
                models.Comment.created_at.desc(),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def repost_post(
        self,
        *,
        post_id: int,
        payload: schemas.RepostCreate,
        current_user: models.User,
    ) -> schemas.PostOut:
        original_post = (
            self.db.query(models.Post).filter(models.Post.id == post_id).first()
        )
        if not original_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Original post not found"
            )
        if (
            not original_post.is_published
            or not original_post.allow_reposts
            or not original_post.owner.allow_reposts
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This post cannot be reposted",
            )
        if original_post.owner_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot repost your own post",
            )
        if not self._check_repost_permissions(original_post, current_user, payload):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to repost this content",
            )

        new_post = models.Post(
            title=f"Repost: {original_post.title}",
            content=payload.content or f"Repost of: {original_post.content}",
            owner_id=current_user.id,
            original_post_id=original_post.id,
            is_repost=True,
            is_published=True,
            category_id=original_post.category_id,
            community_id=payload.community_id or original_post.community_id,
            allow_reposts=payload.allow_reposts,
            share_scope=payload.share_scope,
            sharing_settings={
                "visibility": payload.visibility,
                "custom_message": payload.custom_message,
                "shared_at": datetime.now().isoformat(),
            },
        )
        original_post.repost_count += 1
        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)

        for hashtag in original_post.hashtags:
            new_post.hashtags.append(hashtag)
        self.db.commit()

        update_repost_statistics(self.db, post_id)
        send_repost_notification(
            self.db, original_post.owner_id, current_user.id, new_post.id
        )

        if new_post.share_scope == "community" and new_post.community_id:
            self._notify_community_members(new_post)

        return self._prepare_post_response(new_post, current_user)

    def get_repost_statistics(self, *, post_id: int) -> models.RepostStatistics:
        stats = (
            self.db.query(models.RepostStatistics)
            .filter(models.RepostStatistics.post_id == post_id)
            .first()
        )
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Statistics not found"
            )
        return stats

    def get_reposts(
        self,
        *,
        post_id: int,
        skip: int,
        limit: int,
    ) -> List[schemas.PostOut]:
        post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )
        posts = (
            self.db.query(models.Post)
            .filter(models.Post.original_post_id == post_id)
            .order_by(models.Post.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return self._prepare_post_list(posts)

    def _check_repost_permissions(
        self,
        post: models.Post,
        user: models.User,
        payload: schemas.RepostCreate,
    ) -> bool:
        if not post.allow_reposts:
            return False
        repost_settings = getattr(payload, "repost_settings", None)
        if (
            repost_settings
            and repost_settings.scope == "community"
            and post.shared_with_community_id
        ):
            return self._is_community_member(post.shared_with_community_id, user.id)
        return True

    def _notify_community_members(self, post: models.Post) -> None:
        shared_id = getattr(post, "shared_with_community_id", None)
        if not shared_id:
            return
        members = (
            self.db.query(CommunityMember)
            .filter(CommunityMember.community_id == shared_id)
            .all()
        )
        for member in members:
            create_notification(
                self.db,
                member.user_id,
                f"New shared post in community: {post.title}",
                f"/post/{post.id}",
                "community_share",
                post.id,
            )

    def get_top_reposts(self, *, limit: int) -> List[models.RepostStatistics]:
        return (
            self.db.query(models.RepostStatistics)
            .order_by(models.RepostStatistics.repost_count.desc())
            .limit(limit)
            .all()
        )

    def _is_community_member(self, community_id: int, user_id: int) -> bool:
        return (
            self.db.query(CommunityMember)
            .filter(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == user_id,
            )
            .first()
            is not None
        )

    def _get_comment_reaction_counts(self, comment_id: int) -> List[dict]:
        reactions = (
            self.db.query(
                models.Reaction.reaction_type,
                func.count(models.Reaction.id).label("count"),
            )
            .filter(models.Reaction.comment_id == comment_id)
            .group_by(models.Reaction.reaction_type)
            .all()
        )
        return [{"reaction_type": r.reaction_type, "count": r.count} for r in reactions]

    def toggle_allow_reposts(
        self, *, post_id: int, current_user: models.User
    ) -> schemas.PostOut:
        post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this post",
            )
        post.allow_reposts = not post.allow_reposts
        self.db.commit()
        self.db.refresh(post)
        return self._prepare_post_response(post, current_user)

    def toggle_archive_post(
        self, *, post_id: int, current_user: models.User
    ) -> schemas.PostOut:
        post_query = self.db.query(models.Post).filter(models.Post.id == post_id)
        post = post_query.first()
        if post is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {post_id} does not exist",
            )
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to perform requested action",
            )
        post.is_archived = not post.is_archived
        post.archived_at = func.now() if post.is_archived else None
        self.db.commit()
        self.db.refresh(post)
        return self._prepare_post_response(post, current_user)

    def analyze_existing_post(
        self,
        *,
        post_id: int,
        current_user: models.User,
        analyze_content_fn: Callable[[str], dict],
    ) -> schemas.PostOut:
        post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to analyze this post",
            )
        analysis_result = analyze_content_fn(post.content)
        post.sentiment = analysis_result["sentiment"]["sentiment"]
        post.sentiment_score = analysis_result["sentiment"]["score"]
        post.content_suggestion = analysis_result["suggestion"]
        self.db.commit()
        self.db.refresh(post)
        return self._prepare_post_response(post, current_user)

    def get_posts_with_mentions(
        self,
        *,
        current_user: models.User,
        skip: int,
        limit: int,
        search: str,
        include_archived: bool,
    ) -> List[schemas.PostOut]:
        query = self.db.query(models.Post).filter(
            models.Post.mentioned_users.any(id=current_user.id)
        )
        if not include_archived:
            query = query.filter(models.Post.is_archived.is_(False))
        if search:
            query = query.filter(models.Post.title.contains(search))
        posts = query.offset(skip).limit(limit).all()
        return self._prepare_post_list(posts)

    async def list_posts(
        self,
        *,
        current_user: models.User,
        limit: int,
        skip: int,
        search: str,
        translate: bool,
        translator_fn,
    ) -> list[schemas.PostOut]:
        """
        List posts with optimized eager loading to prevent N+1 queries.

        Improvements:
        - Eager loading of owner and related data
        - Better query structure
        - Proper pagination with validation
        """

        # Build base query with vote aggregation
        query = (
            self.db.query(models.Post, func.count(models.Vote.user_id).label("votes"))
            .join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True)
            .group_by(models.Post.id)
        )

        # Apply search filter if provided
        if search:
            query = query.filter(
                models.Post.title.contains(search)
                | models.Post.content.contains(search)
            )

        # Apply eager loading optimization (prevent N+1 queries)
        # This loads owner, comments, reactions in efficient way
        query = optimize_post_query(query)

        # Order by score descending
        query = query.order_by(models.Post.score.desc())

        # Apply pagination with validation
        query = paginate_query(query, skip, limit)

        # Execute query
        posts = query.all()

        # Process results with optional translation
        result = []
        should_translate = translate and os.getenv("ENABLE_TRANSLATION", "1") == "1"

        for post_obj, _ in posts:
            if should_translate:
                language = (
                    getattr(post_obj, "language", None)
                    or getattr(current_user, "preferred_language", "en")
                    or "en"
                )
                try:
                    post_obj.content = await translator_fn(
                        post_obj.content, current_user, language
                    )
                    post_obj.title = await translator_fn(
                        post_obj.title, current_user, language
                    )
                except TypeError:
                    logger.warning(
                        "Skipping translation for post %s due to TypeError", post_obj.id
                    )

            result.append(schemas.PostOut.model_validate(post_obj))

        return result

    def export_post_as_pdf(self, *, post_id: int) -> bytes:
        post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {post_id} not found",
            )
        pdf = _create_pdf(post)
        if not pdf:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate PDF",
            )
        return pdf.getvalue()

    async def create_audio_post(
        self,
        *,
        background_tasks: BackgroundTasks,
        title: str,
        description: str,
        audio_file: UploadFile,
        current_user: models.User,
        save_audio_fn,
        analyze_content_fn: Callable[[str], dict],
        queue_email_fn: Callable,
        mention_notifier_fn,
    ) -> schemas.PostOut:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
            )
        audio_path = await save_audio_fn(audio_file)
        new_post = models.Post(
            owner_id=current_user.id,
            title=title,
            content=description,
            is_safe_content=True,
            is_audio_post=True,
            audio_url=audio_path,
        )
        mentioned_users = process_mentions(description, self.db)
        new_post.mentioned_users = mentioned_users
        analysis_result = analyze_content_fn(description)
        new_post.sentiment = analysis_result["sentiment"]["sentiment"]
        new_post.sentiment_score = analysis_result["sentiment"]["score"]
        new_post.content_suggestion = analysis_result["suggestion"]
        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)
        log_user_event(
            self.db, current_user.id, "create_audio_post", {"post_id": new_post.id}
        )
        queue_email_fn(
            background_tasks,
            to=current_user.email,
            subject="New Audio Post Created",
            body=f"Your audio post '{new_post.title}' has been created successfully.",
        )
        for user in mentioned_users:
            background_tasks.add_task(
                mention_notifier_fn,
                user.email,
                getattr(current_user, "username", current_user.email),
                new_post.id,
            )
        return self._prepare_post_response(new_post, current_user)

    def get_audio_posts(
        self,
        *,
        skip: int,
        limit: int,
    ) -> List[schemas.PostOut]:
        posts = (
            self.db.query(models.Post)
            .filter(models.Post.is_audio_post.is_(True))
            .order_by(models.Post.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return self._prepare_post_list(posts)

    def create_poll_post(
        self,
        *,
        background_tasks: BackgroundTasks,
        payload: schemas.PollCreate,
        current_user: models.User,
        queue_email_fn: Callable,
    ) -> schemas.PostOut:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
            )
        new_post = models.Post(
            owner_id=current_user.id,
            title=payload.title,
            content=payload.description,
            is_poll=True,
        )
        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)
        for option in payload.options:
            new_option = models.PollOption(post_id=new_post.id, option_text=option)
            self.db.add(new_option)
        if payload.end_date:
            new_poll = models.Poll(post_id=new_post.id, end_date=payload.end_date)
            self.db.add(new_poll)
        self.db.commit()
        log_user_event(
            self.db, current_user.id, "create_poll_post", {"post_id": new_post.id}
        )
        queue_email_fn(
            background_tasks,
            to=current_user.email,
            subject="New Poll Created",
            body=f"Your poll '{new_post.title}' has been created successfully.",
        )
        return self._prepare_post_response(new_post, current_user)

    def vote_in_poll(
        self,
        *,
        post_id: int,
        option_id: int,
        current_user: models.User,
    ) -> dict:
        post = (
            self.db.query(models.Post)
            .filter(models.Post.id == post_id, models.Post.is_poll.is_(True))
            .first()
        )
        if not post:
            raise HTTPException(status_code=404, detail="Poll not found")
        poll = self.db.query(models.Poll).filter(models.Poll.post_id == post_id).first()
        if poll and poll.end_date and poll.end_date < datetime.now():
            raise HTTPException(status_code=400, detail="This poll has ended")
        option = (
            self.db.query(models.PollOption)
            .filter(
                models.PollOption.id == option_id,
                models.PollOption.post_id == post_id,
            )
            .first()
        )
        if not option:
            raise HTTPException(status_code=404, detail="Option not found")
        existing_vote = (
            self.db.query(models.PollVote)
            .filter(
                models.PollVote.user_id == current_user.id,
                models.PollVote.post_id == post_id,
            )
            .first()
        )
        if existing_vote:
            existing_vote.option_id = option_id
        else:
            new_vote = models.PollVote(
                user_id=current_user.id, post_id=post_id, option_id=option_id
            )
            self.db.add(new_vote)
        self.db.commit()
        return {"message": "Vote recorded successfully"}

    def get_poll_results(self, *, post_id: int) -> dict:
        post = (
            self.db.query(models.Post)
            .filter(models.Post.id == post_id, models.Post.is_poll.is_(True))
            .first()
        )
        if not post:
            raise HTTPException(status_code=404, detail="Poll not found")
        poll = self.db.query(models.Poll).filter(models.Poll.post_id == post_id).first()
        options = (
            self.db.query(models.PollOption)
            .filter(models.PollOption.post_id == post_id)
            .all()
        )
        results = []
        total_votes = 0
        for option in options:
            vote_count = (
                self.db.query(func.count(models.PollVote.id))
                .filter(models.PollVote.option_id == option.id)
                .scalar()
            )
            total_votes += vote_count
            results.append(
                {
                    "option_id": option.id,
                    "option_text": option.option_text,
                    "votes": vote_count,
                }
            )
        for result in results:
            result["percentage"] = (
                (result["votes"] / total_votes * 100) if total_votes > 0 else 0
            )
        return {
            "post_id": post_id,
            "total_votes": total_votes,
            "results": results,
            "is_ended": (
                poll.end_date < datetime.now() if poll and poll.end_date else False
            ),
            "end_date": poll.end_date if poll else None,
        }

    def report_content(
        self,
        *,
        current_user: models.User,
        reason: str,
        post_id: int | None = None,
        comment_id: int | None = None,
    ) -> dict:
        return submit_report(
            self.db,
            current_user,
            reason=reason,
            post_id=post_id,
            comment_id=comment_id,
        )
        ...
