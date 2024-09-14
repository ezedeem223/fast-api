from fastapi import (
    APIRouter,
    Depends,
    status,
    HTTPException,
    BackgroundTasks,
)
from sqlalchemy.orm import Session
from .. import models, database, oauth2
from ..notifications import send_email_notification

router = APIRouter(prefix="/follow", tags=["Follow"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
def follow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself"
        )

    follow = (
        db.query(models.Follow)
        .filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.followed_id == user_id,
        )
        .first()
    )

    if follow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already follow this user",
        )

    # التحقق من وجود المستخدم المراد متابعته
    user_to_follow = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User to follow not found",
        )

    new_follow = models.Follow(follower_id=current_user.id, followed_id=user_id)
    db.add(new_follow)
    db.commit()

    # إرسال إشعار بالبريد الإلكتروني عند متابعة مستخدم
    send_email_notification(
        background_tasks=background_tasks,
        to=[user_to_follow.email],  # استخدام البريد الإلكتروني للمستخدم المتابَع
        subject="New Follower",
        body=f"You have a new follower: {current_user.username}",
    )

    return {"message": "Successfully followed user"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
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

    # الحصول على معلومات المستخدم المتابَع
    user_unfollowed = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_unfollowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User to unfollow not found",
        )

    db.delete(follow)
    db.commit()

    # إرسال إشعار بالبريد الإلكتروني عند إلغاء متابعة مستخدم
    send_email_notification(
        background_tasks=background_tasks,
        to=[
            user_unfollowed.email
        ],  # استخدام البريد الإلكتروني للمستخدم الذي تم إلغاء متابعته
        subject="Follower Lost",
        body=f"You have lost a follower: {current_user.username}",
    )

    return {"message": "Successfully unfollowed user"}
