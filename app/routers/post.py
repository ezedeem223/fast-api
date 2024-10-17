from fastapi import (
    FastAPI,
    responses,
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
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, cast, desc
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List, Optional
from ..notifications import send_email_notification, manager, send_mention_notification
from cachetools import cached, TTLCache
import os
from pathlib import Path
import requests
from ..utils import (
    check_content_against_rules,
    log_user_event,
    process_mentions,
    get_or_create_hashtag,
)

from sqlalchemy.dialects.postgresql import JSONB
from ..content_filter import check_content, filter_content
from ..celery_worker import schedule_post_publication
from ..analytics import analyze_content
import aiofiles
from pydub import AudioSegment
import uuid
from datetime import datetime, timedelta


router = APIRouter(prefix="/posts", tags=["Posts"])

cache = TTLCache(maxsize=100, ttl=60)

MEDIA_DIR = Path("static/media")

TWITTER_API_URL = "https://api.twitter.com/2/tweets"
TWITTER_BEARER_TOKEN = "YOUR_TWITTER_BEARER_TOKEN"

FACEBOOK_API_URL = "https://graph.facebook.com/v11.0/me/feed"
FACEBOOK_ACCESS_TOKEN = "YOUR_FACEBOOK_ACCESS_TOKEN"

AUDIO_DIR = Path("static/audio_posts")
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
MAX_AUDIO_DURATION = 300  # 5 minutes in seconds


def share_on_twitter(content: str):
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


@router.get("/search", response_model=List[schemas.PostOut])
def search_posts(
    search: schemas.PostSearch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
def get_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
            detail=f"post with id: {id} was not found",
        )

    reaction_counts = (
        db.query(
            models.Reaction.reaction_type, func.count(models.Reaction.id).label("count")
        )
        .filter(models.Reaction.post_id == id)
        .group_by(models.Reaction.reaction_type)
        .all()
    )

    comments = []
    comments_dict = {}

    for comment in post.comments:
        comment_dict = comment.__dict__
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
            options=poll_options, end_date=post.poll[0].end_date if post.poll else None
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

    return post_out


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.PostOut)
def create_posts(
    background_tasks: BackgroundTasks,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
        logger.warning(f"Content contains warned words: {', '.join(warnings)}")

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
        if not check_content_against_rules(filtered_content, rules):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Post content violates community rules",
            )

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
    )

    for hashtag_name in post.hashtags:
        hashtag = get_or_create_hashtag(db, hashtag_name)
        new_post.hashtags.append(hashtag)

    # Обработка упоминаний
    mentioned_users = process_mentions(post.content, db)
    new_post.mentioned_users = mentioned_users

    if post.analyze_content:
        analysis_result = analyze_content(post.content)
        new_post.sentiment = analysis_result["sentiment"]["sentiment"]
        new_post.sentiment_score = analysis_result["sentiment"]["score"]
        new_post.content_suggestion = analysis_result["suggestion"]

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    log_user_event(db, current_user.id, "create_post", {"post_id": new_post.id})

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
        logger.error(f"Error sharing on social media: {e.detail}")

    if post.scheduled_time:
        schedule_post_publication.apply_async(
            args=[new_post.id], eta=post.scheduled_time
        )
    else:
        send_notifications_and_share(background_tasks, new_post, current_user)

    # Отправка уведомлений упомянутым пользователям
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
    current_user: int = Depends(oauth2.get_current_user),
):
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
    current_user: int = Depends(oauth2.get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    report = models.Report(
        post_id=post_id,
        reported_user_id=post.owner_id,
        reporter_id=current_user.id,
        reason=reason,
    )
    db.add(report)
    db.commit()
    return {"message": "Report submitted successfully"}


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    post_query = db.query(models.Post).filter(models.Post.id == id)
    post = post_query.first()

    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"post with id: {id} does not exist",
        )
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )
    post_query.delete(synchronize_session=False)
    db.commit()
    log_user_event(db, current_user.id, "delete_post", {"post_id": id})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{id}", response_model=schemas.Post)
def update_post(
    id: int,
    updated_post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    post_query = db.query(models.Post).filter(models.Post.id == id)
    post = post_query.first()

    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"post with id: {id} does not exist",
        )
    if post.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )

    if not updated_post.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Content cannot be empty"
        )

    # Обработка новых упоминаний
    new_mentioned_users = process_mentions(updated_post.content, db)
    post.mentioned_users = new_mentioned_users

    post.title = updated_post.title
    post.content = updated_post.content
    post.category_id = updated_post.category_id
    post.is_help_request = updated_post.is_help_request

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
    current_user: int = Depends(oauth2.get_current_user),
):
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    # TODO: Implement check_file_for_safe_content function
    # if not check_file_for_safe_content(video):
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Inappropriate content detected.",
    #     )

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
    followed_users = (
        db.query(models.Follow.followed_id)
        .filter(models.Follow.follower_id == current_user.id)
        .subquery()
    )

    recommended_posts = (
        db.query(models.Post)
        .filter(
            models.Post.owner_id.in_(followed_users)
            | (models.Post.owner_id != current_user.id)
        )
        .order_by(func.random())
        .limit(10)
        .all()
    )

    return recommended_posts


@router.get("/recommendations/", response_model=List[schemas.Post])
def get_recommendations(
    db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)
):
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
    repost_data: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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

    new_post = models.Post(
        title=f"Repost: {original_post.title}",
        content=repost_data.content or f"Repost of: {original_post.content}",
        owner_id=current_user.id,
        original_post_id=original_post.id,
        is_repost=True,
        is_published=True,
        category_id=original_post.category_id,
        community_id=original_post.community_id,
        allow_reposts=repost_data.allow_reposts,
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

    return new_post


@router.get("/reposts/{post_id}", response_model=List[schemas.PostOut])
def get_reposts(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
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


@router.get("/search", response_model=List[schemas.PostOut])
def search_posts(
    keyword: Optional[str] = None,
    hashtag: Optional[str] = None,
    include_reposts: bool = True,
    allow_reposts: Optional[bool] = None,
    sort_by: schemas.SortOption = schemas.SortOption.DATE,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    query = db.query(models.Post)

    if keyword:
        query = query.filter(
            models.Post.title.contains(keyword) | models.Post.content.contains(keyword)
        )
    if hashtag:
        query = query.join(models.Post.hashtags).filter(models.Hashtag.name == hashtag)
    if not include_reposts:
        query = query.filter(models.Post.is_repost == False)
    if allow_reposts is not None:
        query = query.filter(models.Post.allow_reposts == allow_reposts)

    if sort_by == schemas.SortOption.DATE:
        query = query.order_by(desc(models.Post.created_at))
    elif sort_by == schemas.SortOption.REPOST_COUNT:
        query = query.order_by(desc(models.Post.repost_count))
    elif sort_by == schemas.SortOption.POPULARITY:
        query = query.order_by(desc(models.Post.view_count + models.Post.repost_count))

    posts = query.offset(skip).limit(limit).all()
    return posts


@router.post("/{id}/analyze", response_model=schemas.PostOut)
async def analyze_existing_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
):
    posts = (
        db.query(models.Post)
        .filter(models.Post.mentioned_users.any(id=current_user.id))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return posts


async def save_audio_file(file: UploadFile) -> str:
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

    # Process mentions
    mentioned_users = process_mentions(description, db)
    new_post.mentioned_users = mentioned_users

    # Analyze content
    analysis_result = analyze_content(description)
    new_post.sentiment = analysis_result["sentiment"]["sentiment"]
    new_post.sentiment_score = analysis_result["sentiment"]["score"]
    new_post.content_suggestion = analysis_result["suggestion"]

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    log_user_event(db, current_user.id, "create_audio_post", {"post_id": new_post.id})

    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],
        subject="New Audio Post Created",
        body=f"Your new audio post titled '{new_post.title}' has been created successfully.",
    )

    # Notify mentioned users
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
async def create_poll_post(
    background_tasks: BackgroundTasks,
    poll: schemas.PollCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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

    log_user_event(db, current_user.id, "create_poll_post", {"post_id": new_post.id})

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
async def get_poll_results(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
