from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, func
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
from ..notifications import send_email_notification
from ..cache import cache
from datetime import datetime, timedelta
from ..utils import log_user_event, create_notification

router = APIRouter(prefix="/follow", tags=["Follow"])


# Follow Management
@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """متابعة مستخدم"""
    # التحقق من عدم متابعة النفس
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself"
        )

    # التحقق من وجود المستخدم المراد متابعته
    user_to_follow = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found"
        )

    # التحقق من عدم وجود متابعة مسبقة
    existing_follow = (
        db.query(models.Follow)
        .filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.followed_id == user_id,
        )
        .first()
    )

    if existing_follow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already follow this user",
        )

    # إنشاء علاقة المتابعة
    new_follow = models.Follow(follower_id=current_user.id, followed_id=user_id)
    db.add(new_follow)

    # التحقق من المتابعة المتبادلة
    mutual_follow = (
        db.query(models.Follow)
        .filter(
            models.Follow.follower_id == user_id,
            models.Follow.followed_id == current_user.id,
        )
        .first()
    )

    if mutual_follow:
        new_follow.is_mutual = True
        mutual_follow.is_mutual = True

    # تحديث عداد المتابعين
    user_to_follow.followers_count += 1
    current_user.following_count += 1

    db.commit()

    # تسجيل الحدث
    log_user_event(db, current_user.id, "follow_user", {"followed_id": user_id})

    # إرسال الإشعارات
    background_tasks.add_task(
        send_email_notification,
        to=user_to_follow.email,
        subject="New Follower",
        body=f"You have a new follower: {current_user.email}",
    )

    create_notification(
        db,
        user_id,
        f"{current_user.username} بدأ بمتابعتك",
        f"/profile/{current_user.id}",
        "new_follower",
        current_user.id,
    )

    return {"message": "Successfully followed user"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إلغاء متابعة مستخدم"""
    follow = (
        db.query(models.Follow)
        .filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.followed_id == user_id,
        )
        .first()
    )

    if not follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="You do not follow this user"
        )

    user_unfollowed = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_unfollowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User to unfollow not found"
        )

    # إلغاء علامة المتابعة المتبادلة إذا وجدت
    if follow.is_mutual:
        mutual_follow = (
            db.query(models.Follow)
            .filter(
                models.Follow.follower_id == user_id,
                models.Follow.followed_id == current_user.id,
            )
            .first()
        )
        if mutual_follow:
            mutual_follow.is_mutual = False

    db.delete(follow)

    # تحديث عداد المتابعين
    user_unfollowed.followers_count -= 1
    current_user.following_count -= 1

    db.commit()

    # إرسال إشعار بالبريد
    background_tasks.add_task(
        send_email_notification,
        to=user_unfollowed.email,
        subject="Follower Lost",
        body=f"You have lost a follower: {current_user.email}",
    )

    return None


# Followers and Following Lists
@router.get("/followers", response_model=schemas.FollowersListOut)
@cache(expire=300)
async def get_followers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    sort_by: str = Query("date", enum=["date", "username"]),
    order: str = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    """الحصول على قائمة المتابعين"""
    query = db.query(models.Follow).filter(models.Follow.followed_id == current_user.id)

    # تطبيق الترتيب
    if sort_by == "date":
        order_column = models.Follow.created_at
    elif sort_by == "username":
        order_column = models.User.username

    if order == "desc":
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(asc(order_column))

    total_count = query.count()
    followers = (
        query.join(models.User, models.Follow.follower_id == models.User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "followers": [
            schemas.FollowerOut(
                id=follow.follower.id,
                username=follow.follower.username,
                follow_date=follow.created_at,
                post_count=follow.follower.post_count,
                interaction_count=follow.follower.interaction_count,
                is_mutual=follow.is_mutual,
            )
            for follow in followers
        ],
        "total_count": total_count,
    }


@router.get("/following", response_model=schemas.FollowingListOut)
@cache(expire=300)
async def get_following(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    sort_by: str = Query("date", enum=["date", "username"]),
    order: str = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    """الحصول على قائمة المتابَعين"""
    query = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id)

    # تطبيق الترتيب
    if sort_by == "date":
        order_column = models.Follow.created_at
    elif sort_by == "username":
        order_column = models.User.username

    if order == "desc":
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(asc(order_column))

    total_count = query.count()
    following = (
        query.join(models.User, models.Follow.followed_id == models.User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "following": [
            schemas.FollowingOut(
                id=follow.followed.id,
                username=follow.followed.username,
                email=follow.followed.email,
                follow_date=follow.created_at,
                is_mutual=follow.is_mutual,
            )
            for follow in following
        ],
        "total_count": total_count,
    }


# Statistics and Analytics
@router.get("/statistics", response_model=schemas.FollowStatistics)
def get_follow_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على إحصائيات المتابعة"""
    # حساب نمو المتابعين في الأيام الـ 30 الماضية
    thirty_days_ago = datetime.now() - timedelta(days=30)
    daily_growth = (
        db.query(func.date(models.Follow.created_at), func.count())
        .filter(
            models.Follow.followed_id == current_user.id,
            models.Follow.created_at >= thirty_days_ago,
        )
        .group_by(func.date(models.Follow.created_at))
        .all()
    )

    # حساب معدل التفاعل
    interaction_rate = (
        db.query(func.count(models.Post.id) + func.count(models.Comment.id))
        .filter(
            (models.Post.owner_id == current_user.id)
            | (models.Comment.owner_id == current_user.id)
        )
        .scalar()
        / current_user.followers_count
        if current_user.followers_count > 0
        else 0
    )

    return {
        "followers_count": current_user.followers_count,
        "following_count": current_user.following_count,
        "daily_growth": dict(daily_growth),
        "interaction_rate": interaction_rate,
    }


@router.get("/mutual", response_model=List[schemas.UserOut])
def get_mutual_followers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على قائمة المتابعين المتبادلين"""
    mutual_followers = (
        db.query(models.User)
        .join(models.Follow, models.User.id == models.Follow.follower_id)
        .filter(
            models.Follow.followed_id == current_user.id,
            models.Follow.is_mutual == True,
        )
        .all()
    )
    return mutual_followers
