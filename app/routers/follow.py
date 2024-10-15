from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
from ..notifications import send_email_notification
from ..cache import cache

router = APIRouter(prefix="/follow", tags=["Follow"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself"
        )

    user_to_follow = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found"
        )

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

    new_follow = models.Follow(follower_id=current_user.id, followed_id=user_id)
    db.add(new_follow)

    user_to_follow.followers_count += 1

    db.commit()

    background_tasks.add_task(
        send_email_notification,
        to=user_to_follow.email,
        subject="New Follower",
        body=f"You have a new follower: {current_user.email}",
    )

    return {"message": "Successfully followed user"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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

    user_unfollowed = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_unfollowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User to unfollow not found",
        )

    db.delete(follow)

    user_unfollowed.followers_count -= 1

    db.commit()

    background_tasks.add_task(
        send_email_notification,
        to=user_unfollowed.email,
        subject="Follower Lost",
        body=f"You have lost a follower: {current_user.email}",
    )

    return None


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
    query = db.query(models.Follow).filter(models.Follow.followed_id == current_user.id)

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
    query = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id)

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
            )
            for follow in following
        ],
        "total_count": total_count,
    }
