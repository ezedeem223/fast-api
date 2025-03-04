# app/routers/post.py

"""
This module defines the API endpoints for managing posts in the social media application.
It includes functionalities for:
    - Searching, creating, updating, and deleting posts.
    - Uploading media files (images, audio, short videos).
    - Handling reposts, poll posts, comments, notifications, and exporting posts as PDF.
    
Helper functions and global constants are defined at the beginning to organize the code.
"""

# =====================================================
# ================  Imports Section  ==================
# =====================================================

from fastapi import (
    FastAPI,
    Response,
    status,
    HTTPException,
    Depends,
    APIRouter,
    BackgroundTasks,
    UploadFile,
    File,
    Query,
    Form,
)
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, cast, desc
from sqlalchemy.dialects.postgresql import JSONB
from typing import List, Optional
import os
from pathlib import Path
import requests
import aiofiles
from pydub import AudioSegment
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from xhtml2pdf import pisa
from cachetools import cached, TTLCache

# Import local modules
from .. import models, schemas, oauth2, utils
from ..database import get_db
from ..i18n import translate_text, get_translated_content
from ..notifications import send_email_notification, manager, send_mention_notification
from ..content_filter import check_content, filter_content
from ..celery_worker import schedule_post_publication
from ..analytics import analyze_content
from ..media_processing import process_media_file
from app.notifications import NotificationService, send_real_time_notification

# =====================================================
# ==============  Global Constants  ===================
# =====================================================

router = APIRouter(prefix="/posts", tags=["Posts"])
cache = TTLCache(maxsize=100, ttl=60)

MEDIA_DIR = Path("static/media")
AUDIO_DIR = Path("static/audio_posts")
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
MAX_AUDIO_DURATION = 300  # Maximum audio duration in seconds (5 minutes)

TWITTER_API_URL = "https://api.twitter.com/2/tweets"
TWITTER_BEARER_TOKEN = "YOUR_TWITTER_BEARER_TOKEN"

FACEBOOK_API_URL = "https://graph.facebook.com/v11.0/me/feed"
FACEBOOK_ACCESS_TOKEN = "YOUR_FACEBOOK_ACCESS_TOKEN"

# =====================================================
# ================  Helper Functions  =================
# =====================================================


def share_on_twitter(content: str):
    """
    Shares a given content on Twitter using the Twitter API.
    """
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {"text": content}
    response = requests.post(TWITTER_API_URL, headers=headers, json=data)
    if response.status_code != 201:
        raise HTTPException(
            status_code=response.status_code,
            detail="Failed to share post on Twitter",
        )


def share_on_facebook(content: str):
    """
    Shares a given content on Facebook using the Facebook API.
    """
    params = {
        "access_token": FACEBOOK_ACCESS_TOKEN,
        "message": content,
    }
    response = requests.post(FACEBOOK_API_URL, params=params)
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="Failed to share post on Facebook",
        )


async def save_audio_file(file: UploadFile) -> str:
    """
    Saves the uploaded audio file asynchronously.
    Checks if the file extension is allowed and verifies the audio duration.
    Returns the file path if successful.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    file_extension = os.path.splitext(file.filename)[1]
    if file_extension.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio file format")

    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = AUDIO_DIR / unique_filename

    async with aiofiles.open(file_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    # Check audio duration
    audio = AudioSegment.from_file(file_path)
    duration_seconds = len(audio) / 1000
    if duration_seconds > MAX_AUDIO_DURATION:
        os.remove(file_path)
        raise HTTPException(
            status_code=400, detail="Audio file exceeds maximum duration"
        )

    return str(file_path)


def create_pdf(post: models.Post):
    """
    Generates a PDF file from a post's content.
    Returns a BytesIO object containing the PDF data if successful.
    """
    html = f"""
    <html>
    <head>
        <title>{post.title}</title>
    </head>
    <body>
        <h1>{post.title}</h1>
        <p>Posted by: {post.owner.username}</p>
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


def check_repost_permissions(
    post: models.Post, user: models.User, repost_data: schemas.RepostCreate
) -> bool:
    """
    Check if the given user is allowed to repost the specified post.
    If the repost settings indicate a 'community' scope, further check membership.
    """
    if not post.allow_reposts:
        return False

    if repost_data.repost_settings and repost_data.repost_settings.scope == "community":
        # is_community_member should be implemented in utils or another module
        return utils.is_community_member(post.shared_with_community_id, user.id)

    return True


def notify_community_members(db: Session, post: models.Post):
    """
    Send notifications to community members for a shared post.
    """
    members = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == post.shared_with_community_id)
        .all()
    )

    for member in members:
        utils.send_notification(
            member.user_id,
            f"New shared post in community: {post.title}",
            post.id,
        )


async def get_translated_content_async(
    content: str, user: models.User, source_lang: str
) -> str:
    """
    Asynchronously translate the provided content to the user's preferred language if needed.
    """
    if user.auto_translate and user.preferred_language != source_lang:
        return await translate_text(content, source_lang, user.preferred_language)
    return content


# =====================================================
# =================  API Endpoints  ===================
# =====================================================


@router.get("/search", response_model=List[schemas.PostOut])
def search_posts(
    search: schemas.PostSearch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Search for posts based on a structured search input (keyword, category_id, hashtag).
    """
    query = db.query(models.Post)
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
    return posts


@router.get("/{id}", response_model=schemas.PostOut)
async def get_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve a single post by its ID along with related data (comments, reactions, poll options, etc.).
    Also applies translation on post title and content if required.
    """
    post_query = (
        db.query(models.Post)
        .options(
            joinedload(models.Post.comments).joinedload(models.Comment.replies),
            joinedload(models.Post.reactions),
            joinedload(models.Post.mentioned_users),
            joinedload(models.Post.poll_options),
            joinedload(models.Post.poll),
        )
        .filter(models.Post.id == id)
    )

    post = post_query.first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {id} was not found",
        )

    reaction_counts = (
        db.query(
            models.Reaction.reaction_type, func.count(models.Reaction.id).label("count")
        )
        .filter(models.Reaction.post_id == id)
        .group_by(models.Reaction.reaction_type)
        .all()
    )

    # Process comments and their nested replies
    comments = []
    comments_dict = {}
    for comment in post.comments:
        comment_dict = comment.__dict__.copy()
        comment_dict["replies"] = []
        comment_dict["reactions"] = [
            schemas.Reaction(id=r.id, user_id=r.user_id, reaction_type=r.reaction_type)
            for r in comment.reactions
        ]
        comment_dict["reaction_counts"] = utils.get_comment_reaction_counts(
            comment.id, db
        )
        comments_dict[comment.id] = comment_dict
        if comment.parent_id is None:
            comments.append(comment_dict)
        else:
            parent = comments_dict.get(comment.parent_id)
            if parent:
                parent["replies"].append(comment_dict)

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
            schemas.Reaction(id=r.id, user_id=r.user_id, reaction_type=r.reaction_type)
            for r in post.reactions
        ],
        reaction_counts=[
            schemas.ReactionCount(reaction_type=r.reaction_type, count=r.count)
            for r in reaction_counts
        ],
        comments=comments,
        mentioned_users=[
            schemas.UserOut.from_orm(user) for user in post.mentioned_users
        ],
        sentiment=post.sentiment,
        sentiment_score=post.sentiment_score,
        content_suggestion=post.content_suggestion,
        is_audio_post=post.is_audio_post,
        audio_url=post.audio_url if post.is_audio_post else None,
        is_poll=post.is_poll,
        poll_data=poll_data,
    )

    # Apply translation asynchronously
    post_out.content = await get_translated_content_async(
        post.content, current_user, post.language
    )
    post_out.title = await get_translated_content_async(
        post.title, current_user, post.language
    )
    return post_out


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut)
def create_posts(
    background_tasks: BackgroundTasks,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new post after validating content, checking for banned words, filtering content,
    processing mentions, and handling hashtags. Also triggers notifications and social media sharing.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )
    if not post.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Content cannot be empty"
        )

    warnings, bans = check_content(db, post.content)
    if bans:
        raise HTTPException(
            status_code=400, detail=f"Content contains banned words: {', '.join(bans)}"
        )
    if warnings:
        # Log warnings if necessary
        utils.logger.warning(f"Content contains warned words: {', '.join(warnings)}")

    filtered_content = filter_content(db, post.content)

    if post.community_id:
        community = (
            db.query(models.Community)
            .filter(models.Community.id == post.community_id)
            .first()
        )
        if not community:
            raise HTTPException(status_code=404, detail="Community not found")
        rules = [rule.rule for rule in community.rules]
        if not check_content(db, filtered_content)[
            0
        ]:  # Using check_content_against_rules if available
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Post content violates community rules",
            )

    # If a media file is provided (this branch may be used for image uploads)
    # Note: The variable 'file' should be obtained via form-data if used.
    # if file:
    #     file_path = f"uploads/{file.filename}"
    #     with open(file_path, "wb") as buffer:
    #         buffer.write(await file.read())
    #     new_post.media_url = file_path
    #     new_post.media_type = file.content_type
    #     new_post.media_text = process_media_file(file_path)

    new_post = models.Post(
        owner_id=current_user.id,
        title=post.title,
        content=filtered_content,
        is_safe_content=True,
        community_id=post.community_id,
        is_help_request=post.is_help_request,
        category_id=post.category_id,
        scheduled_time=post.scheduled_time,
        is_published=post.scheduled_time is None,
        copyright_type=post.copyright_type,
        custom_copyright=post.custom_copyright,
    )

    # Process hashtags
    for hashtag_name in post.hashtags:
        hashtag = utils.get_or_create_hashtag(db, hashtag_name)
        new_post.hashtags.append(hashtag)

    # Process mentions
    mentioned_users = utils.process_mentions(post.content, db)
    new_post.mentioned_users = mentioned_users

    if post.analyze_content:
        analysis_result = analyze_content(post.content)
        new_post.sentiment = analysis_result["sentiment"]["sentiment"]
        new_post.sentiment_score = analysis_result["sentiment"]["score"]
        new_post.content_suggestion = analysis_result["suggestion"]

    is_offensive, confidence = utils.is_content_offensive(new_post.content)
    if is_offensive:
        new_post.is_flagged = True
        new_post.flag_reason = (
            f"AI detected potentially offensive content (confidence: {confidence:.2f})"
        )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    utils.log_user_event(db, current_user.id, "create_post", {"post_id": new_post.id})

    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],
        subject="New Post Created",
        body=f"Your new post titled '{new_post.title}' has been created successfully.",
    )
    background_tasks.add_task(manager.broadcast, f"New post created: {new_post.title}")

    try:
        share_on_twitter(new_post.content)
        share_on_facebook(new_post.content)
    except HTTPException as e:
        utils.logger.error(f"Error sharing on social media: {e.detail}")

    if post.scheduled_time:
        schedule_post_publication.apply_async(
            args=[new_post.id], eta=post.scheduled_time
        )
    else:
        utils.send_notifications_and_share(background_tasks, new_post, current_user)

    # Notify mentioned users
    for user in mentioned_users:
        background_tasks.add_task(
            send_mention_notification, user.email, current_user.username, new_post.id
        )

    return new_post


@router.get("/scheduled", response_model=List[schemas.PostOut])
def get_scheduled_posts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve posts that have a scheduled time and are not yet published.
    """
    scheduled_posts = (
        db.query(models.Post)
        .filter(
            models.Post.owner_id == current_user.id,
            models.Post.scheduled_time.isnot(None),
            models.Post.is_published == False,
        )
        .all()
    )
    return scheduled_posts


@router.post("/upload_file/", status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Handle file uploads and create a post with the file location as content.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    file_location = MEDIA_DIR / file.filename

    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())

    new_post = models.Post(
        owner_id=current_user.id,
        title=file.filename,
        content=str(file_location),
        is_safe_content=True,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return {"message": "File uploaded successfully", "post_id": new_post.id}


@router.post("/report/", status_code=status.HTTP_201_CREATED)
def report_post(
    post_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Report a post with a given reason. Also, flag the post if offensive content is detected.
    """
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    is_offensive, confidence = utils.is_content_offensive(post.content)

    report = models.Report(
        post_id=post_id,
        reported_user_id=post.owner_id,
        reporter_id=current_user.id,
        reason=reason,
        ai_detected=is_offensive,
        ai_confidence=confidence,
    )
    db.add(report)
    if is_offensive and not post.is_flagged:
        post.is_flagged = True
        post.flag_reason = (
            f"AI detected offensive content (confidence: {confidence:.2f})"
        )
    db.commit()
    db.refresh(report)
    return {"message": "Report submitted successfully"}


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Delete a post by its ID if the current user is the owner.
    """
    post_query = db.query(models.Post).filter(models.Post.id == id)
    post = post_query.first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {id} does not exist",
        )
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )
    post_query.delete(synchronize_session=False)
    db.commit()
    utils.log_user_event(db, current_user.id, "delete_post", {"post_id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{id}", response_model=schemas.Post)
def update_post(
    id: int,
    updated_post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update an existing post with new content and information.
    Processes new mentions and triggers notifications for followers.
    """
    post_query = db.query(models.Post).filter(models.Post.id == id)
    post = post_query.first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {id} does not exist",
        )
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )

    if updated_post.copyright_type is not None:
        post.copyright_type = updated_post.copyright_type
    if updated_post.custom_copyright is not None:
        post.custom_copyright = updated_post.custom_copyright
    if not updated_post.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Content cannot be empty"
        )

    # Process new mentions
    new_mentioned_users = utils.process_mentions(updated_post.content, db)
    post.mentioned_users = new_mentioned_users

    post.title = updated_post.title
    post.content = updated_post.content
    post.category_id = updated_post.category_id
    post.is_help_request = updated_post.is_help_request

    followers = (
        db.query(models.Follow)
        .filter(models.Follow.followed_id == current_user.id)
        .all()
    )
    for follower in followers:
        utils.create_notification(
            db,
            follower.follower_id,
            f"{current_user.username} قام بتحديث منشور",
            f"/post/{post.id}",
            "post_update",
            post.id,
        )

    if updated_post.analyze_content:
        analysis_result = analyze_content(updated_post.content)
        post.sentiment = analysis_result["sentiment"]["sentiment"]
        post.sentiment_score = analysis_result["sentiment"]["score"]
        post.content_suggestion = analysis_result["suggestion"]

    db.commit()
    db.refresh(post)
    return post


@router.post("/short_videos/", status_code=status.HTTP_201_CREATED)
def create_short_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a short video post.
    Note: A function to check for safe content (e.g. check_file_for_safe_content) is recommended.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    # TODO: Implement check_file_for_safe_content function if needed.
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    file_location = MEDIA_DIR / video.filename
    with open(file_location, "wb+") as file_object:
        file_object.write(video.file.read())

    new_post = models.Post(
        owner_id=current_user.id,
        title=video.filename,
        content=str(file_location),
        is_safe_content=True,
        is_short_video=True,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],
        subject="New Short Video Created",
        body=f"Your new short video titled '{new_post.title}' has been created successfully.",
    )
    return {"message": "Short video uploaded successfully", "post_id": new_post.id}


@cached(cache)
def get_recommendations_cached(db: Session, current_user: int):
    """
    Returns cached post recommendations based on the posts of followed users and others.
    """
    followed_users = (
        db.query(models.Follow.followed_id)
        .filter(models.Follow.follower_id == current_user)
        .subquery()
    )
    recommended_posts = (
        db.query(models.Post)
        .filter(
            models.Post.owner_id.in_(followed_users)
            | (models.Post.owner_id != current_user)
        )
        .order_by(func.random())
        .limit(10)
        .all()
    )
    return recommended_posts


@router.get("/recommendations/", response_model=List[schemas.Post])
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Returns post recommendations by combining posts from followed users and other posts,
    ordered by vote count, comment count, and creation date.
    """
    followed_users = (
        db.query(models.Follow.followed_id)
        .filter(models.Follow.follower_id == current_user.id)
        .subquery()
    )
    recommended_posts = (
        db.query(models.Post)
        .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
        .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
        .filter(models.Post.owner_id.in_(followed_users))
        .group_by(models.Post.id)
        .order_by(
            func.count(models.Vote.id).desc(),
            func.count(models.Comment.id).desc(),
            models.Post.created_at.desc(),
        )
        .limit(10)
        .all()
    )

    other_posts = (
        db.query(models.Post)
        .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
        .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
        .filter(
            models.Post.owner_id.notin_(followed_users),
            models.Post.owner_id != current_user.id,
        )
        .group_by(models.Post.id)
        .order_by(
            func.count(models.Vote.id).desc(),
            func.count(models.Comment.id).desc(),
            models.Post.created_at.desc(),
        )
        .limit(5)
        .all()
    )

    return recommended_posts + other_posts


@router.get("/{post_id}/comments", response_model=List[schemas.CommentOut])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve comments for a specific post ordered by pinning and creation date.
    """
    comments = (
        db.query(models.Comment)
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
    return comments


@router.post(
    "/repost/{post_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
)
def repost(
    post_id: int,
    repost_data: schemas.RepostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a repost of an existing post.
    Checks for permissions and updates repost count and statistics.
    """
    original_post = db.query(models.Post).filter(models.Post.id == post_id).first()
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

    if not check_repost_permissions(original_post, current_user, repost_data):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to repost this content",
        )

    new_post = models.Post(
        title=f"Repost: {original_post.title}",
        content=repost_data.content or f"Repost of: {original_post.content}",
        owner_id=current_user.id,
        original_post_id=original_post.id,
        is_repost=True,
        is_published=True,
        category_id=original_post.category_id,
        community_id=repost_data.community_id or original_post.community_id,
        allow_reposts=repost_data.allow_reposts,
        share_scope=repost_data.share_scope,
        sharing_settings={
            "visibility": repost_data.visibility,
            "custom_message": repost_data.custom_message,
            "shared_at": datetime.now().isoformat(),
        },
    )
    original_post.repost_count += 1
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    for hashtag in original_post.hashtags:
        new_post.hashtags.append(hashtag)

    utils.update_repost_statistics(db, post_id)
    utils.send_repost_notification(
        db, original_post.owner_id, current_user.id, new_post.id
    )

    if new_post.share_scope == "community" and new_post.community_id:
        notify_community_members(db, new_post)

    return new_post


@router.get("/post/{post_id}/repost-stats", response_model=schemas.RepostStatsOut)
def get_repost_statistics(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve repost statistics for a specific post.
    """
    stats = (
        db.query(models.RepostStatistics)
        .filter(models.RepostStatistics.post_id == post_id)
        .first()
    )
    if not stats:
        raise HTTPException(status_code=404, detail="Statistics not found")
    return stats


@router.get("/reposts/{post_id}", response_model=List[schemas.PostOut])
def get_reposts(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    """
    Retrieve reposts for a given original post.
    """
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    reposts = (
        db.query(models.Post)
        .filter(models.Post.original_post_id == post_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return reposts


@router.get("/top-reposts", response_model=List[schemas.RepostStatisticsOut])
def get_top_reposts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    limit: int = Query(10, le=100),
):
    """
    Retrieve top repost statistics ordered by repost count.
    """
    top_reposts = (
        db.query(models.RepostStatistics)
        .order_by(desc(models.RepostStatistics.repost_count))
        .limit(limit)
        .all()
    )
    return top_reposts


@router.put("/toggle-reposts/{post_id}", response_model=schemas.PostOut)
def toggle_allow_reposts(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Toggle the allow_reposts flag for a given post.
    Only the post owner is allowed to modify this setting.
    """
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
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
    db.commit()
    db.refresh(post)
    return post


@router.post("/{id}/analyze", response_model=schemas.PostOut)
async def analyze_existing_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Analyze an existing post to update its sentiment, sentiment score, and content suggestion.
    Only the post owner is allowed to perform this analysis.
    """
    post = db.query(models.Post).filter(models.Post.id == id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to analyze this post"
        )
    analysis_result = analyze_content(post.content)
    post.sentiment = analysis_result["sentiment"]["sentiment"]
    post.sentiment_score = analysis_result["sentiment"]["score"]
    post.content_suggestion = analysis_result["suggestion"]
    db.commit()
    db.refresh(post)
    return post


@router.get("/mentions", response_model=List[schemas.PostOut])
def get_posts_with_mentions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = "",
    include_archived: bool = False,
):
    """
    Retrieve posts where the current user is mentioned.
    Optionally filter by search term and whether to include archived posts.
    """
    query = db.query(models.Post)
    if not include_archived:
        query = query.filter(models.Post.is_archived == False)
    if search:
        query = query.filter(models.Post.title.contains(search))
    posts = (
        db.query(models.Post)
        .filter(models.Post.mentioned_users.any(id=current_user.id))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return posts


@router.post(
    "/audio", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut
)
async def create_audio_post(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    audio_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create an audio post by saving the uploaded audio file,
    processing mentions, and analyzing the content for sentiment.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )
    audio_path = await save_audio_file(audio_file)
    new_post = models.Post(
        owner_id=current_user.id,
        title=title,
        content=description,
        is_safe_content=True,
        is_audio_post=True,
        audio_url=audio_path,
    )
    mentioned_users = utils.process_mentions(description, db)
    new_post.mentioned_users = mentioned_users
    analysis_result = analyze_content(description)
    new_post.sentiment = analysis_result["sentiment"]["sentiment"]
    new_post.sentiment_score = analysis_result["sentiment"]["score"]
    new_post.content_suggestion = analysis_result["suggestion"]
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    utils.log_user_event(
        db, current_user.id, "create_audio_post", {"post_id": new_post.id}
    )
    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],
        subject="New Audio Post Created",
        body=f"Your new audio post titled '{new_post.title}' has been created successfully.",
    )
    for user in mentioned_users:
        background_tasks.add_task(
            send_mention_notification, user.email, current_user.username, new_post.id
        )
    return new_post


@router.get("/audio", response_model=List[schemas.PostOut])
def get_audio_posts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    """
    Retrieve posts that are audio posts, ordered by creation date.
    """
    audio_posts = (
        db.query(models.Post)
        .filter(models.Post.is_audio_post == True)
        .order_by(models.Post.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return audio_posts


@router.post(
    "/poll", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut
)
def create_poll_post(
    background_tasks: BackgroundTasks,
    poll: schemas.PollCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a poll post along with its options and optional end date.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )
    new_post = models.Post(
        owner_id=current_user.id,
        title=poll.title,
        content=poll.description,
        is_poll=True,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    for option in poll.options:
        new_option = models.PollOption(post_id=new_post.id, option_text=option)
        db.add(new_option)
    if poll.end_date:
        new_poll = models.Poll(post_id=new_post.id, end_date=poll.end_date)
        db.add(new_poll)
    db.commit()
    utils.log_user_event(
        db, current_user.id, "create_poll_post", {"post_id": new_post.id}
    )
    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],
        subject="New Poll Created",
        body=f"Your new poll '{new_post.title}' has been created successfully.",
    )
    return new_post


@router.post("/{post_id}/vote", status_code=status.HTTP_200_OK)
async def vote_in_poll(
    post_id: int,
    option_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Record a vote for a poll option in a poll post.
    """
    post = (
        db.query(models.Post)
        .filter(models.Post.id == post_id, models.Post.is_poll == True)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Poll not found")
    poll = db.query(models.Poll).filter(models.Poll.post_id == post_id).first()
    if poll and poll.end_date < datetime.now():
        raise HTTPException(status_code=400, detail="This poll has ended")
    option = (
        db.query(models.PollOption)
        .filter(models.PollOption.id == option_id, models.PollOption.post_id == post_id)
        .first()
    )
    if not option:
        raise HTTPException(status_code=404, detail="Option not found")
    existing_vote = (
        db.query(models.PollVote)
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
        db.add(new_vote)
    db.commit()
    return {"message": "Vote recorded successfully"}


@router.get("/{post_id}/poll-results", response_model=schemas.PollResults)
def get_poll_results(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve the results of a poll post including vote counts and percentages.
    """
    post = (
        db.query(models.Post)
        .filter(models.Post.id == post_id, models.Post.is_poll == True)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Poll not found")
    poll = db.query(models.Poll).filter(models.Poll.post_id == post_id).first()
    options = (
        db.query(models.PollOption).filter(models.PollOption.post_id == post_id).all()
    )
    results = []
    total_votes = 0
    for option in options:
        vote_count = (
            db.query(func.count(models.PollVote.id))
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
        "is_ended": poll.end_date < datetime.now() if poll else False,
        "end_date": poll.end_date if poll else None,
    }


@router.put("/{id}/archive", response_model=schemas.PostOut)
def archive_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Toggle the archived status of a post.
    """
    post_query = db.query(models.Post).filter(models.Post.id == id)
    post = post_query.first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {id} does not exist",
        )
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )
    post.is_archived = not post.is_archived
    post.archived_at = func.now() if post.is_archived else None
    db.commit()
    return post


@router.get("/", response_model=List[schemas.PostOut])
async def get_posts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    limit: int = 10,
    skip: int = 0,
    search: Optional[str] = "",
):
    """
    Retrieve posts along with aggregated vote counts.
    Applies translation for post content and title.
    """
    posts = (
        db.query(models.Post, func.count(models.Vote.user_id).label("votes"))
        .join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True)
        .group_by(models.Post.id)
        .filter(models.Post.title.contains(search))
        .order_by(models.Post.score.desc())
        .limit(limit)
        .offset(skip)
        .all()
    )

    # Translate each post's title and content asynchronously
    for post_tuple in posts:
        post_obj = post_tuple[0]
        post_obj.content = await get_translated_content_async(
            post_obj.content, current_user, post_obj.language
        )
        post_obj.title = await get_translated_content_async(
            post_obj.title, current_user, post_obj.language
        )
    # Extract only the Post objects from the tuple
    return [post_tuple[0] for post_tuple in posts]


@router.get("/{id}/export-pdf")
def export_post_as_pdf(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Export a specific post as a PDF file.
    """
    post = db.query(models.Post).filter(models.Post.id == id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {id} not found",
        )
    pdf = create_pdf(post)
    if not pdf:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF",
        )
    return StreamingResponse(
        iter([pdf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=post_{id}.pdf"},
    )


# =====================================================
# ============  Notification Handler Class  ===========
# =====================================================


class PostNotificationHandler:
    """
    Handles notifications related to post creation.
    It sends notifications to followers and community members if applicable.
    """

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_post_creation(self, post: models.Post, current_user: models.User):
        # Notify followers
        followers = (
            self.db.query(models.Follow)
            .filter(models.Follow.followed_id == current_user.id)
            .all()
        )
        for follower in followers:
            await self.notification_service.create_notification(
                user_id=follower.follower_id,
                content=f"{current_user.username} نشر منشوراً جديداً",
                notification_type="new_post",
                priority=models.NotificationPriority.MEDIUM,
                category=models.NotificationCategory.SOCIAL,
                link=f"/post/{post.id}",
                metadata={
                    "post_id": post.id,
                    "post_title": post.title,
                    "author_id": current_user.id,
                    "author_name": current_user.username,
                },
            )
        # Notify community members if the post belongs to a community
        if post.community_id:
            members = (
                self.db.query(models.CommunityMember)
                .filter(models.CommunityMember.community_id == post.community_id)
                .all()
            )
            for member in members:
                if member.user_id != current_user.id:
                    await self.notification_service.create_notification(
                        user_id=member.user_id,
                        content=f"منشور جديد في المجتمع من {current_user.username}",
                        notification_type="community_post",
                        priority=models.NotificationPriority.LOW,
                        category=models.NotificationCategory.COMMUNITY,
                        link=f"/post/{post.id}",
                    )
