from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas, oauth2
from typing import List, Optional
from datetime import datetime
import praw
import json
from linkedin_api import Linkedin

router = APIRouter(prefix="/social/posts", tags=["Social Media Posts"])


@router.post("/", response_model=schemas.SocialPostOut)
async def create_social_post(
    post: schemas.SocialPostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    # Check if user has connected account for the platform
    account = (
        db.query(models.SocialMediaAccount)
        .filter(
            models.SocialMediaAccount.user_id == current_user.id,
            models.SocialMediaAccount.platform == post.platform,
            models.SocialMediaAccount.is_active == True,
        )
        .first()
    )

    if not account:
        raise HTTPException(
            status_code=404, detail=f"No connected {post.platform} account found"
        )

    new_post = models.SocialMediaPost(
        user_id=current_user.id,
        account_id=account.id,
        title=post.title,
        content=post.content,
        media_urls=post.media_urls,
        scheduled_for=post.scheduled_for,
        status=(
            schemas.PostStatus.SCHEDULED
            if post.scheduled_for
            else schemas.PostStatus.DRAFT
        ),
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    if not post.scheduled_for:
        background_tasks.add_task(publish_social_post, new_post.id, db)

    return new_post


@router.get("/", response_model=List[schemas.SocialPostOut])
async def get_social_posts(
    platform: Optional[schemas.SocialMediaType] = None,
    status: Optional[schemas.PostStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    query = db.query(models.SocialMediaPost).filter(
        models.SocialMediaPost.user_id == current_user.id
    )

    if platform:
        query = query.join(models.SocialMediaAccount).filter(
            models.SocialMediaAccount.platform == platform
        )

    if status:
        query = query.filter(models.SocialMediaPost.status == status)

    posts = query.offset(skip).limit(limit).all()
    return posts


@router.get("/{post_id}", response_model=schemas.SocialPostOut)
async def get_social_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    post = (
        db.query(models.SocialMediaPost)
        .filter(
            models.SocialMediaPost.id == post_id,
            models.SocialMediaPost.user_id == current_user.id,
        )
        .first()
    )

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return post

    async def delete_social_post(
        post_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(oauth2.get_current_user),
    ):
        post = (
            db.query(models.SocialMediaPost)
            .filter(
                models.SocialMediaPost.id == post_id,
                models.SocialMediaPost.user_id == current_user.id,
            )
            .first()
        )

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if post.status == schemas.PostStatus.PUBLISHED:
            raise HTTPException(status_code=400, detail="Cannot delete published post")

        db.delete(post)
        db.commit()

        return {"message": "Post deleted successfully"}


@router.put("/{post_id}", response_model=schemas.SocialPostOut)
async def update_social_post(
    post_id: int,
    post_update: schemas.SocialPostUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    post = (
        db.query(models.SocialMediaPost)
        .filter(
            models.SocialMediaPost.id == post_id,
            models.SocialMediaPost.user_id == current_user.id,
        )
        .first()
    )

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status == schemas.PostStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Cannot update published post")

    for key, value in post_update.dict(exclude_unset=True).items():
        setattr(post, key, value)

    db.commit()
    db.refresh(post)

    return post


async def publish_social_post(post_id: int, db: Session):
    """وظيفة خلفية لنشر المنشور على المنصة المحددة"""
    post = (
        db.query(models.SocialMediaPost)
        .filter(models.SocialMediaPost.id == post_id)
        .first()
    )
    if not post:
        return

    account = (
        db.query(models.SocialMediaAccount)
        .filter(models.SocialMediaAccount.id == post.account_id)
        .first()
    )
    if not account:
        post.status = schemas.PostStatus.FAILED
        post.error_message = "Social media account not found"
        db.commit()
        return

    try:
        if account.platform == schemas.SocialMediaType.REDDIT:
            await publish_to_reddit(post, account)
        elif account.platform == schemas.SocialMediaType.LINKEDIN:
            await publish_to_linkedin(post, account)

        post.status = schemas.PostStatus.PUBLISHED
        post.published_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        post.status = schemas.PostStatus.FAILED
        post.error_message = str(e)
        db.commit()


async def publish_to_reddit(
    post: models.SocialMediaPost, account: models.SocialMediaAccount
):
    """نشر المحتوى على Reddit"""
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        refresh_token=account.refresh_token,
        user_agent=settings.REDDIT_USER_AGENT,
    )

    # التحقق من صلاحية التوكن وتحديثه إذا لزم الأمر
    if account.token_expires_at < datetime.now(timezone.utc):
        new_token_info = reddit.auth.refresh_token()
        account.access_token = new_token_info["access_token"]
        account.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=new_token_info["expires_in"]
        )

    subreddit = reddit.subreddit(post.metadata.get("subreddit", "test"))

    # إنشاء المنشور على Reddit
    if post.media_urls:
        reddit_post = subreddit.submit_image(
            title=post.title,
            image_path=post.media_urls[0],
            flair_id=post.metadata.get("flair_id"),
        )
    else:
        reddit_post = subreddit.submit(
            title=post.title,
            selftext=post.content,
            flair_id=post.metadata.get("flair_id"),
        )

    post.platform_post_id = reddit_post.id
    return reddit_post.id


async def publish_to_linkedin(
    post: models.SocialMediaPost, account: models.SocialMediaAccount
):
    """نشر المحتوى على LinkedIn"""
    api = Linkedin(access_token=account.access_token)

    # التحقق من صلاحية التوكن وتحديثه إذا لزم الأمر
    if account.token_expires_at < datetime.now(timezone.utc):
        new_token = await refresh_linkedin_token(account)
        account.access_token = new_token["access_token"]
        account.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=new_token["expires_in"]
        )

    # إعداد محتوى المنشور
    post_data = {
        "author": f"urn:li:person:{account.account_username}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post.content},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": post.metadata.get(
                "visibility", "PUBLIC"
            )
        },
    }

    # إضافة الوسائط إذا وجدت
    if post.media_urls:
        media_assets = []
        for url in post.media_urls:
            asset = await api.upload_media(url)
            media_assets.append(
                {
                    "status": "READY",
                    "media": asset["asset"],
                    "title": {"text": post.title or ""},
                }
            )

        post_data["specificContent"]["com.linkedin.ugc.ShareContent"][
            "shareMediaCategory"
        ] = "IMAGE"
        post_data["specificContent"]["com.linkedin.ugc.ShareContent"][
            "media"
        ] = media_assets

    # نشر المحتوى
    response = await api.post_share(post_data)
    post.platform_post_id = response["id"]
    return response["id"]


@router.get("/{post_id}/stats", response_model=schemas.EngagementStats)
async def get_post_stats(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على إحصائيات التفاعل مع المنشور"""
    post = (
        db.query(models.SocialMediaPost)
        .filter(
            models.SocialMediaPost.id == post_id,
            models.SocialMediaPost.user_id == current_user.id,
        )
        .first()
    )

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status != schemas.PostStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Post is not published yet")

    try:
        stats = await update_post_stats(post)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def update_post_stats(post: models.SocialMediaPost):
    """تحديث إحصائيات التفاعل مع المنشور"""
    account = (
        db.query(models.SocialMediaAccount)
        .filter(models.SocialMediaAccount.id == post.account_id)
        .first()
    )

    if account.platform == schemas.SocialMediaType.REDDIT:
        reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            refresh_token=account.refresh_token,
            user_agent=settings.REDDIT_USER_AGENT,
        )

        reddit_post = reddit.submission(id=post.platform_post_id)
        stats = {
            "upvotes": reddit_post.ups,
            "downvotes": reddit_post.downs,
            "comments": reddit_post.num_comments,
            "score": reddit_post.score,
        }

    elif account.platform == schemas.SocialMediaType.LINKEDIN:
        api = Linkedin(access_token=account.access_token)
        post_stats = await api.get_post_stats(post.platform_post_id)

        stats = {
            "likes": post_stats.get("numLikes", 0),
            "comments": post_stats.get("numComments", 0),
            "shares": post_stats.get("numShares", 0),
            "impressions": post_stats.get("totalShareStatistics", {}).get(
                "impressionCount", 0
            ),
        }

    post.engagement_stats = stats
    db.commit()

    return stats


# إضافة مهام دورية
from fastapi_utils.tasks import repeat_every


@router.on_event("startup")
@repeat_every(seconds=3600)  # تحديث كل ساعة
def update_all_post_stats():
    """تحديث إحصائيات جميع المنشورات المنشورة دورياً"""
    db = next(get_db())
    posts = (
        db.query(models.SocialMediaPost)
        .filter(models.SocialMediaPost.status == schemas.PostStatus.PUBLISHED)
        .all()
    )

    for post in posts:
        try:
            update_post_stats(post)
        except Exception as e:
            print(f"Error updating stats for post {post.id}: {e}")


@router.on_event("startup")
@repeat_every(seconds=300)  # كل 5 دقائق
def publish_scheduled_posts():
    """نشر المنشورات المجدولة"""
    db = next(get_db())
    now = datetime.now(timezone.utc)

    scheduled_posts = (
        db.query(models.SocialMediaPost)
        .filter(
            models.SocialMediaPost.status == schemas.PostStatus.SCHEDULED,
            models.SocialMediaPost.scheduled_for <= now,
        )
        .all()
    )

    for post in scheduled_posts:
        try:
            publish_social_post(post.id, db)
        except Exception as e:
            print(f"Error publishing scheduled post {post.id}: {e}")
