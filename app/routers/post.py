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
from sqlalchemy import func
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional
from ..notifications import send_email_notification, manager
from cachetools import cached, TTLCache
import os
from pathlib import Path
import requests

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


@router.get("/", response_model=List[schemas.PostOut])
def get_posts(
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
    limit: int = 10,
    skip: int = 0,
    search: Optional[str] = "",
):
    posts = (
        db.query(models.Post, func.count(models.Vote.post_id).label("votes"))
        .join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True)
        .group_by(models.Post.id)
        .filter(models.Post.title.contains(search))
        .limit(limit)
        .offset(skip)
        .all()
    )

    return posts


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Post)
def create_posts(
    background_tasks: BackgroundTasks,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    new_post = models.Post(
        owner_id=current_user.id,
        content=post.content,
        is_safe_content=True,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # إرسال إشعار بالبريد الإلكتروني عند إنشاء منشور جديد
    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],  # استخدام البريد الإلكتروني للمستخدم الحالي
        subject="New Post Created",
        body=f"Your new post titled '{new_post.title}' has been created successfully.",
    )
    background_tasks.add_task(manager.broadcast, f"New post created: {new_post.title}")

    # مشاركة المحتوى على الشبكات الاجتماعية
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
    return post


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
    if not check_file_for_safe_content(video):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inappropriate content detected.",
        )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    file_location = MEDIA_DIR / video.filename

    with open(file_location, "wb+") as file_object:
        file_object.write(video.file.read())

    new_post = models.Post(
        owner_id=current_user.id,
        content=str(file_location),
        is_safe_content=True,
        is_short_video=True,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # إرسال إشعار بالبريد الإلكتروني عند إنشاء فيديو قصير جديد
    send_email_notification(
        background_tasks=background_tasks,
        to=[current_user.email],  # استخدام البريد الإلكتروني للمستخدم الحالي
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


def get_recommendations(db: Session, current_user: int):
    # الحصول على قائمة المستخدمين الذين يتابعهم المستخدم الحالي
    followed_users = (
        db.query(models.Follow.followed_id)
        .filter(models.Follow.follower_id == current_user.id)
        .subquery()
    )

    # استرجاع المنشورات الموصى بها بناءً على المتابعة والتفاعلات
    recommended_posts = (
        db.query(models.Post)
        .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
        .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
        .filter(models.Post.owner_id.in_(followed_users))
        .group_by(models.Post.id)
        .order_by(
            func.count(models.Vote.id).desc(),  # الترتيب حسب عدد الأصوات
            func.count(models.Comment.id).desc(),  # الترتيب حسب عدد التعليقات
            models.Post.created_at.desc(),  # إعطاء الأولوية للمنشورات الأحدث
        )
        .limit(10)
        .all()
    )

    # عرض منشورات مقترحة أخرى من مستخدمين غير متابعين ولكن لهم محتوى قد يعجب المستخدم
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
        .limit(5)  # يمكن تعديل العدد حسب الحاجة
        .all()
    )

    # دمج القائمتين معًا
    return recommended_posts + other_posts
