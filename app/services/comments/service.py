"""Service layer handling comment operations."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

import emoji
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload

from app import notifications
from app.notifications import (
    create_notification,
    queue_email_notification,
    schedule_email_notification,
)
from app.modules.posts.models import Comment, Post
from app.modules.amenhotep.models import CommentEditHistory
from app.modules.social.models import Report
from app.modules.users.models import User
from app.modules.utils.content import (
    check_content_against_rules,
    check_for_profanity,
    validate_urls,
    analyze_sentiment,
    is_valid_image_url,
    is_valid_video_url,
    detect_language,
)
from app.modules.utils.events import log_user_event
from app.modules.utils.common import get_user_display_name
from app.modules.utils.translation import get_translated_content
from app.modules.utils.analytics import update_post_score
from app.modules.social.economy_service import SocialEconomyService

if TYPE_CHECKING:
    from app import schemas


class CommentService:
    """Encapsulates comment creation logic."""

    def __init__(self, db: Session):
        self.db = db

    async def create_comment(
        self,
        *,
        schema: "schemas.CommentCreate",
        current_user: User,
        background_tasks: BackgroundTasks,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        notification_module=notifications,
        create_notification_fn=create_notification,
    ) -> Comment:
        """Create a new comment and trigger notifications."""

        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
            )

        post = self.db.query(Post).filter(Post.id == schema.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )

        await self._validate_comment_content(schema, post)

        new_comment = Comment(
            owner_id=current_user.id,
            post_id=schema.post_id,
            parent_id=schema.parent_id,
            content=schema.content,
            image_url=schema.image_url,
            video_url=schema.video_url,
            has_emoji=emoji.emoji_count(schema.content) > 0,
            has_sticker=schema.sticker_id is not None,
            sticker_id=schema.sticker_id,
            language=detect_language(schema.content),
        )

        new_comment.contains_profanity = check_for_profanity(schema.content)
        new_comment.has_invalid_urls = not validate_urls(schema.content)
        new_comment.sentiment_score = analyze_sentiment(schema.content)

        current_user.comment_count += 1
        post.comment_count += 1

        self.db.add(new_comment)
        self.db.commit()
        self.db.refresh(new_comment)

        # =============== START Social Economy Update ===============
        try:
            # Update post score because comments increase engagement
            economy_service = SocialEconomyService(self.db)
            economy_service.update_post_score(schema.post_id)
        except Exception as e:
            logging.getLogger(__name__).error(
                f"Error updating social score after comment: {e}"
            )
        # =============== END Social Economy Update =================

        commenter_name = get_user_display_name(current_user)
        log_user_event(
            self.db,
            current_user.id,
            "create_comment",
            {"comment_id": new_comment.id, "post_id": schema.post_id},
        )

        create_notification_fn(
            self.db,
            post.owner_id,
            f"{commenter_name} commented on your post",
            f"/post/{post.id}",
            "new_comment",
            new_comment.id,
        )

        if schema.parent_id:
            parent_comment = (
                self.db.query(Comment).filter(Comment.id == schema.parent_id).first()
            )
            if parent_comment and parent_comment.owner_id != post.owner_id:
                create_notification_fn(
                    self.db,
                    parent_comment.owner_id,
                    f"{commenter_name} replied to your comment",
                    f"/post/{post.id}#comment-{new_comment.id}",
                    "reply_to_comment",
                    new_comment.id,
                )

        update_post_score(self.db, post)

        queue_email_fn(
            background_tasks,
            to=post.owner.email,
            subject="New Comment on Your Post",
            body=f"A new comment has been added to your post '{post.title}'.",
        )
        schedule_email_fn(
            background_tasks,
            to=post.owner.email,
            subject="New Comment on Your Post",
            body=f"A new comment has been added to your post '{post.title}'.",
        )

        broadcast_message = f"User {current_user.id} has commented on post {post.id}."
        comment_broadcast = notification_module.manager.broadcast
        if asyncio.iscoroutinefunction(comment_broadcast):
            background_tasks.add_task(asyncio.run, comment_broadcast(broadcast_message))
        else:
            comment_broadcast(broadcast_message)

        return new_comment

    def delete_comment(self, *, comment_id: int, current_user: User) -> dict:
        """Soft delete a comment owned by the current user."""
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )

        if comment.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this comment",
            )

        comment.is_deleted = True
        comment.deleted_at = datetime.now(comment.created_at.tzinfo)
        comment.content = "[Deleted]"

        self.db.commit()
        return {"message": "Comment deleted successfully"}

    def update_comment(
        self,
        *,
        comment_id: int,
        payload: "schemas.CommentUpdate",
        current_user: User,
        edit_window: Optional[timedelta],
    ) -> Comment:
        """Update a comment's content within the allowed edit window."""
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )

        if comment.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to edit this comment",
            )

        if (
            edit_window
            and datetime.now(comment.created_at.tzinfo) - comment.created_at
            > edit_window
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Edit window has expired",
            )

        edit_history = CommentEditHistory(
            comment_id=comment.id, previous_content=comment.content
        )
        self.db.add(edit_history)

        comment.content = payload.content
        comment.is_edited = True
        comment.edited_at = datetime.now(comment.created_at.tzinfo)

        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_edit_history(self, *, comment_id: int, current_user: User):
        """Return edit history for a comment if requester is owner or moderator."""
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )

        if current_user.id != comment.owner_id and not getattr(
            current_user, "is_moderator", False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view comment history",
            )

        return comment.edit_history

    def report_content(
        self,
        *,
        payload: "schemas.ReportCreate",
        current_user: User,
    ) -> Report:
        """Create a report for a post or comment and auto-flag if needed."""
        if payload.post_id:
            post = self.db.query(Post).filter(Post.id == payload.post_id).first()
            if not post:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
                )
            reported_content = post.content
            reported_owner_id = post.owner_id
            content_target = post
        elif payload.comment_id:
            comment = (
                self.db.query(Comment).filter(Comment.id == payload.comment_id).first()
            )
            if not comment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
                )
            reported_content = comment.content
            reported_owner_id = comment.owner_id
            content_target = comment
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either post_id or comment_id must be provided",
            )

        contains_profanity = check_for_profanity(reported_content)
        has_invalid_urls = not validate_urls(reported_content)

        new_report = Report(
            reporter_id=current_user.id,
            post_id=payload.post_id,
            comment_id=payload.comment_id,
            reported_user_id=reported_owner_id,
            report_reason=payload.report_reason,
            contains_profanity=contains_profanity,
            has_invalid_urls=has_invalid_urls,
        )
        self.db.add(new_report)

        if contains_profanity or has_invalid_urls:
            content_target.is_flagged = True
            content_target.flag_reason = "Automatic content check"

        self.db.commit()
        self.db.refresh(new_report)
        return new_report

    async def list_comments(
        self,
        *,
        post_id: int,
        current_user: User,
        sort_by: str,
        sort_order: str,
        skip: int,
        limit: int,
    ):
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )

        query = self.db.query(Comment).filter(
            Comment.post_id == post_id, Comment.parent_id.is_(None)
        )

        order_column = (
            Comment.likes_count if sort_by == "likes_count" else Comment.created_at
        )
        query = query.order_by(
            desc(order_column) if sort_order == "desc" else asc(order_column)
        )

        if not current_user.is_moderator:
            query = query.filter(Comment.is_flagged.is_(False))

        comments = (
            query.options(joinedload(Comment.replies)).offset(skip).limit(limit).all()
        )

        for comment in comments:
            comment.content = await get_translated_content(
                comment.content, current_user, comment.language
            )

        return comments

    def list_replies(
        self,
        *,
        comment_id: int,
        current_user: User,
        sort_by: str,
        sort_order: str,
    ):
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )

        query = self.db.query(Comment).filter(Comment.parent_id == comment_id)

        order_column = (
            Comment.likes_count if sort_by == "likes_count" else Comment.created_at
        )
        query = query.order_by(
            desc(order_column) if sort_order == "desc" else asc(order_column)
        )

        if not current_user.is_moderator:
            query = query.filter(Comment.is_flagged.is_(False))

        return query.all()

    def like_comment(self, *, comment_id: int) -> dict:
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        comment.likes_count += 1
        self.db.commit()
        return {"message": "Comment liked successfully"}

    def toggle_highlight(self, *, comment_id: int, current_user: User) -> Comment:
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        post = self.db.query(Post).filter(Post.id == comment.post_id).first()
        if post.owner_id != current_user.id and not getattr(
            current_user, "is_moderator", False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to highlight this comment",
            )

        comment.is_highlighted = not comment.is_highlighted
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def set_best_answer(
        self,
        *,
        comment_id: int,
        current_user: User,
    ) -> Comment:
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        post = self.db.query(Post).filter(Post.id == comment.post_id).first()
        if post.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to set best answer",
            )

        previous_best = (
            self.db.query(Comment)
            .filter(Comment.post_id == post.id, Comment.is_best_answer.is_(True))
            .first()
        )
        if previous_best:
            previous_best.is_best_answer = False

        comment.is_best_answer = True
        post.has_best_answer = True
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def toggle_pin(
        self,
        *,
        comment_id: int,
        current_user: User,
    ) -> Comment:
        comment = self.db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        post = self.db.query(Post).filter(Post.id == comment.post_id).first()
        if post.owner_id != current_user.id and not getattr(
            current_user, "is_moderator", False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to pin this comment",
            )

        if comment.is_pinned:
            pinned_comments_count = (
                self.db.query(Comment)
                .filter(Comment.post_id == post.id, Comment.is_pinned.is_(True))
                .count()
            )
            if (
                hasattr(post, "max_pinned_comments")
                and post.max_pinned_comments is not None
                and pinned_comments_count >= post.max_pinned_comments
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Maximum number of pinned comments "
                        f"({post.max_pinned_comments}) reached for this post"
                    ),
                )

        comment.is_pinned = not comment.is_pinned
        comment.pinned_at = datetime.now(timezone.utc) if comment.is_pinned else None

        self.db.commit()
        self.db.refresh(comment)
        return comment

    async def _validate_comment_content(
        self, comment: "schemas.CommentCreate", post: Post
    ) -> None:
        """Validate comment content against rules and media constraints."""
        if post.community_id:
            community_rules = [rule.rule for rule in post.community.rules]
            if not check_content_against_rules(comment.content, community_rules):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Comment content violates community rules",
                )

        if comment.image_url and not is_valid_image_url(comment.image_url):
            raise HTTPException(status_code=400, detail="Invalid image URL")

        if comment.video_url and not is_valid_video_url(comment.video_url):
            raise HTTPException(status_code=400, detail="Invalid video URL")
