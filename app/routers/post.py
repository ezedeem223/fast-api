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
)
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, cast
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional
from ..notifications import send_email_notification, manager
from cachetools import cached, TTLCache
import os
from pathlib import Path
import requests
from ..utils import check_content_against_rules
from sqlalchemy.dialects.postgresql import JSONB


router = APIRouter(prefix="/posts", tags=["Posts"])

cache = TTLCache(maxsize=100, ttl=60)

MEDIA_DIR = Path("static/media")

TWITTER_API_URL = "https://api.twitter.com/2/tweets"
TWITTER_BEARER_TOKEN = "YOUR_TWITTER_BEARER_TOKEN"

FACEBOOK_API_URL = "https://graph.facebook.com/v11.0/me/feed"
FACEBOOK_ACCESS_TOKEN = "YOUR_FACEBOOK_ACCESS_TOKEN"


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
        )
        .filter(models.Post.id == id)
    )

    post = post_query.first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"post with id: {id} was not found",
        )

    # Получение реакций для поста
    reaction_counts = (
        db.query(
            models.Reaction.reaction_type, func.count(models.Reaction.id).label("count")
        )
        .filter(models.Reaction.post_id == id)
        .group_by(models.Reaction.reaction_type)
        .all()
    )

    # Организация комментариев в древовидную структуру
    comments = []
    comments_dict = {}

    for comment in post.comments:
        comment_dict = comment.__dict__
        comment_dict["replies"] = []
        comment_dict["reactions"] = [
            schemas.Reaction(id=r.id, user_id=r.user_id, reaction_type=r.reaction_type)
            for r in comment.reactions
        ]
        comment_dict["reaction_counts"] = get_comment_reaction_counts(comment.id, db)
        comments_dict[comment.id] = comment_dict
        if comment.parent_id is None:
            comments.append(comment_dict)
        else:
            parent = comments_dict.get(comment.parent_id)
            if parent:
                parent["replies"].append(comment_dict)

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
    )

    return post_out


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Post)
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

    # التحقق من قواعد المجتمع
    if post.community_id:
        community = (
            db.query(models.Community)
            .filter(models.Community.id == post.community_id)
            .first()
        )
        if not community:
            raise HTTPException(status_code=404, detail="Community not found")

        rules = [rule.rule for rule in community.rules]
        if not check_content_against_rules(post.content, rules):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Post content violates community rules",
            )

    new_post = models.Post(
        owner_id=current_user.id,
        title=post.title,
        content=post.content,
        is_safe_content=True,
        community_id=post.community_id,
        is_help_request=post.is_help_request,  # أضف هذا الحقل
    )

    for hashtag_name in post.hashtags:
        hashtag = (
            db.query(models.Hashtag).filter(models.Hashtag.name == hashtag_name).first()
        )
        if not hashtag:
            hashtag = models.Hashtag(name=hashtag_name)
            db.add(hashtag)
        new_post.hashtags.append(hashtag)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

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
        print(f"Error sharing on social media: {e.detail}")

    return new_post


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
    report = models.Report(post_id=post_id, user_id=current_user.id, reason=reason)
    db.add(report)
    db.commit()
    return {"message": "Report submitted successfully"}


@router.get("/{id}", response_model=schemas.PostOut)
def get_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    post = (
        db.query(models.Post, func.count(models.Vote.post_id).label("votes"))
        .join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True)
        .group_by(models.Post.id)
        .filter(models.Post.id == id)
        .first()
    )

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"post with id: {id} was not found",
        )
    return schemas.PostOut(post=post[0], votes=post[1])


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
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{id}", response_model=schemas.Post)
def update_post(
    id: int,
    update_post: schemas.PostCreate,
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

    if not update_post.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Content cannot be empty"
        )

    post_query.update(update_post.model_dump(), synchronize_session=False)
    db.commit()
    return post_query.first()


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
