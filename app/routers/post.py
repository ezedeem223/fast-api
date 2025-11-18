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
from typing import List, Optional, Union
import inspect
import os
import logging
from pathlib import Path
import requests
import aiofiles
import uuid
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from cachetools import cached, TTLCache

# Import local modules
from .. import models, schemas, oauth2, notifications
from app.modules.community import Community, CommunityMember
from app.core.config import settings
from app.core.database import get_db
from ..i18n import translate_text, get_translated_content
from ..content_filter import check_content, filter_content
from ..celery_worker import schedule_post_publication
from ..analytics import analyze_content
from ..media_processing import process_media_file
from app.notifications import NotificationService, send_real_time_notification, send_email_notification, queue_email_notification, schedule_email_notification
from ..services.reporting import submit_report
from app.services.posts import PostService

# =====================================================
# ==============  Global Constants  ===================
# =====================================================

router = APIRouter(prefix="/posts", tags=["Posts"])
cache = TTLCache(maxsize=100, ttl=60)
logger = logging.getLogger(__name__)


def get_post_service(db: Session = Depends(get_db)) -> PostService:
    """Provide a PostService instance for route handlers."""
    return PostService(db)


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


def _social_sharing_configured(token: str) -> bool:
    return bool(token and not token.startswith("YOUR_"))


def share_on_twitter(content: str):
    """
    Shares a given content on Twitter using the Twitter API.
    """
    if not _social_sharing_configured(TWITTER_BEARER_TOKEN):
        logger.info("Twitter credentials not configured; skipping share.")
        return
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {"text": content}
    try:
        response = requests.post(TWITTER_API_URL, headers=headers, json=data, timeout=10)
        if response.status_code != 201:
            logger.warning("Twitter share failed: %s", response.text)
            if settings.environment.lower() == "production":
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to share post on Twitter",
                )
    except requests.RequestException as exc:
        logger.warning("Twitter share request error: %s", exc)
        if settings.environment.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to share post on Twitter",
            )


def share_on_facebook(content: str):
    """
    Shares a given content on Facebook using the Facebook API.
    """
    if not _social_sharing_configured(FACEBOOK_ACCESS_TOKEN):
        logger.info("Facebook credentials not configured; skipping share.")
        return
    params = {
        "access_token": FACEBOOK_ACCESS_TOKEN,
        "message": content,
    }
    try:
        response = requests.post(FACEBOOK_API_URL, params=params, timeout=10)
        if response.status_code != 200:
            logger.warning("Facebook share failed: %s", response.text)
            if settings.environment.lower() == "production":
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to share post on Facebook",
                )
    except requests.RequestException as exc:
        logger.warning("Facebook share request error: %s", exc)
        if settings.environment.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to share post on Facebook",
            )


async def save_audio_file(file: UploadFile) -> str:
    """
    Saves the uploaded audio file asynchronously.
    Checks if the file extension is allowed and verifies the audio duration.
    Returns the file path if successful.
    """
    from pydub import AudioSegment  # Local import avoids import-time warnings during tests
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
    from xhtml2pdf import pisa  # Local import defers reportlab side effects during tests

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


async def get_translated_content_async(
    content: str, user: models.User, source_lang: str
) -> str:
    """
    Asynchronously translate the provided content to the user's preferred language if needed.
    """
    return content


# =====================================================
# =================  API Endpoints  ===================
# =====================================================


@router.get("/search", response_model=List[schemas.PostOut])
def search_posts(
    search: schemas.PostSearch,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Search for posts based on keyword/category/hashtag filters."""
    return service.search_posts(search=search, current_user=current_user)

@router.get("/{id}", response_model=schemas.PostOut)
async def get_post(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Retrieve a single post and related aggregates."""
    return await service.get_post(
        post_id=id,
        current_user=current_user,
        translator_fn=get_translated_content_async,
    )

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut)
def create_posts(
    background_tasks: BackgroundTasks,
    post: schemas.PostCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Create a new post after validating content and triggering side-effects."""
    return service.create_post(
        background_tasks=background_tasks,
        payload=post,
        current_user=current_user,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        broadcast_fn=notifications.manager.broadcast,
        share_on_twitter_fn=share_on_twitter,
        share_on_facebook_fn=share_on_facebook,
        mention_notifier_fn=notifications.send_mention_notification,
        analyze_content_fn=analyze_content,
    )

@router.get("/scheduled", response_model=List[schemas.PostOut])
def get_scheduled_posts(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Retrieve scheduled posts for the authenticated user."""
    return service.get_scheduled_posts(current_user=current_user)


@router.post("/upload_file/", status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Handle file uploads and create a post pointing to the stored media."""
    new_post = service.upload_file_post(
        file=file,
        current_user=current_user,
        media_dir=MEDIA_DIR,
    )
    return {"message": "File uploaded successfully", "post_id": new_post.id}


@router.post("/report/", status_code=status.HTTP_201_CREATED)
def report_post(
    report: schemas.ReportCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Report a post or comment with a given reason. Also, flag the content if offensive text is detected.
    """
    return service.report_content(
        current_user=current_user,
        reason=report.reason,
        post_id=report.post_id,
        comment_id=report.comment_id,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Delete a post if the requester is the owner."""
    service.delete_post(post_id=id, current_user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{id}", response_model=schemas.Post)
def update_post(
    id: int,
    updated_post: schemas.PostCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Update an existing post with new content and information using the shared service layer.
    """
    return service.update_post(
        post_id=id,
        payload=updated_post,
        current_user=current_user,
        analyze_content_fn=analyze_content,
    )


@router.post("/short_videos/", status_code=status.HTTP_201_CREATED)
def create_short_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Create a short video post.
    Note: A function to check for safe content (e.g. check_file_for_safe_content) is recommended.
    """
    new_post = service.create_short_video(
        background_tasks=background_tasks,
        file=video,
        current_user=current_user,
        media_dir=MEDIA_DIR,
        queue_email_fn=queue_email_notification,
    )
    return {"message": "Short video uploaded successfully", "post_id": new_post.id}


@router.get("/recommendations/", response_model=List[schemas.Post])
def get_recommendations(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """Return post recommendations by combining followed and other posts."""
    return service.get_recommendations(current_user=current_user)


@router.get("/{post_id}/comments", response_model=List[schemas.CommentOut])
def get_comments(
    post_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve comments for a specific post ordered by pinning and creation date.
    """
    return service.list_post_comments(post_id=post_id, skip=skip, limit=limit)


@router.post(
    "/repost/{post_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
)
def repost(
    post_id: int,
    repost_data: schemas.RepostCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Create a repost of an existing post.
    Checks for permissions and updates repost count and statistics.
    """
    return service.repost_post(
        post_id=post_id, payload=repost_data, current_user=current_user
    )


@router.get("/post/{post_id}/repost-stats", response_model=schemas.RepostStatisticsOut)
def get_repost_statistics(
    post_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Retrieve repost statistics for a specific post.
    """
    return service.get_repost_statistics(post_id=post_id)


@router.get("/reposts/{post_id}", response_model=List[schemas.PostOut])
def get_reposts(
    post_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    skip: int = 0,
    limit: int = 10,
):
    """
    Retrieve reposts for a given original post.
    """
    return service.get_reposts(post_id=post_id, skip=skip, limit=limit)


@router.get("/top-reposts", response_model=List[schemas.RepostStatisticsOut])
def get_top_reposts(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    limit: int = Query(10, le=100),
):
    """
    Retrieve top repost statistics ordered by repost count.
    """
    return service.get_top_reposts(limit=limit)


@router.put("/toggle-reposts/{post_id}", response_model=schemas.PostOut)
def toggle_allow_reposts(
    post_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Toggle the allow_reposts flag for a given post.
    Only the post owner is allowed to modify this setting.
    """
    return service.toggle_allow_reposts(post_id=post_id, current_user=current_user)


@router.post("/{id}/analyze", response_model=schemas.PostOut)
async def analyze_existing_post(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Analyze an existing post to update its sentiment, sentiment score, and content suggestion.
    Only the post owner is allowed to perform this analysis.
    """
    return service.analyze_existing_post(
        post_id=id,
        current_user=current_user,
        analyze_content_fn=analyze_content,
    )


@router.get("/mentions", response_model=List[schemas.PostOut])
def get_posts_with_mentions(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = "",
    include_archived: bool = False,
):
    """
    Retrieve posts where the current user is mentioned.
    Optionally filter by search term and whether to include archived posts.
    """
    return service.get_posts_with_mentions(
        current_user=current_user,
        skip=skip,
        limit=limit,
        search=search or "",
        include_archived=include_archived,
    )


@router.post(
    "/audio", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut
)
async def create_audio_post(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    audio_file: UploadFile = File(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Create an audio post by saving the uploaded audio file,
    processing mentions, and analyzing the content for sentiment.
    """
    return await service.create_audio_post(
        background_tasks=background_tasks,
        title=title,
        description=description,
        audio_file=audio_file,
        current_user=current_user,
        save_audio_fn=save_audio_file,
        analyze_content_fn=analyze_content,
        queue_email_fn=queue_email_notification,
        mention_notifier_fn=notifications.send_mention_notification,
    )


@router.get("/audio", response_model=List[schemas.PostOut])
def get_audio_posts(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    skip: int = 0,
    limit: int = 10,
):
    """
    Retrieve posts that are audio posts, ordered by creation date.
    """
    return service.get_audio_posts(skip=skip, limit=limit)


@router.post(
    "/poll", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut
)
def create_poll_post(
    background_tasks: BackgroundTasks,
    poll: schemas.PollCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Create a poll post along with its options and optional end date.
    """
    return service.create_poll_post(
        background_tasks=background_tasks,
        payload=poll,
        current_user=current_user,
        queue_email_fn=queue_email_notification,
    )


@router.post("/{post_id}/vote", status_code=status.HTTP_200_OK)
async def vote_in_poll(
    post_id: int,
    option_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Record a vote for a poll option in a poll post.
    """
    return service.vote_in_poll(
        post_id=post_id, option_id=option_id, current_user=current_user
    )


@router.get("/{post_id}/poll-results", response_model=schemas.PollResults)
def get_poll_results(
    post_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Retrieve the results of a poll post including vote counts and percentages.
    """
    return service.get_poll_results(post_id=post_id)


@router.put("/{id}/archive", response_model=schemas.PostOut)
def archive_post(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
):
    """
    Toggle the archived status of a post.
    """
    return service.toggle_archive_post(post_id=id, current_user=current_user)


@router.get("/", response_model=List[schemas.PostOut])
async def get_posts(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: PostService = Depends(get_post_service),
    limit: int = 10,
    skip: int = 0,
    search: Optional[str] = "",
    translate: bool = Query(False, description="Set to true to translate post title/content to the user's preferred language"),
):
    """
    Retrieve posts along with aggregated vote counts.
    Applies translation for post content and title.
    """
    return await service.list_posts(
        current_user=current_user,
        limit=limit,
        skip=skip,
        search=search or "",
        translator_fn=get_translated_content_async,
        translate=translate,
    )


@router.get("/{id}/export-pdf")
def export_post_as_pdf(
    id: int,
    service: PostService = Depends(get_post_service),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Export a specific post as a PDF file."""
    pdf_bytes = service.export_post_as_pdf(post_id=id)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=post_{id}.pdf"},
    )


# =====================================================
# ============  Notification Handler Class  ===========
# =====================================================
