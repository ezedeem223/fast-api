from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from typing import List
from datetime import datetime, timedelta
from .. import models, schemas, oauth2
from ..database import get_db
from ..notifications import send_email_notification
from ..cache import cache
from ..utils import log_user_event, create_notification

router = APIRouter(prefix="/follow", tags=["Follow"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Follow a user.

    Parameters:
      - user_id: ID of the user to follow.
      - background_tasks: Background tasks manager.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Prevent following oneself.
      - Check if the user to follow exists.
      - Verify that the user is not already followed.
      - Create a new follow record.
      - Check for mutual follow and update accordingly.
      - Update followers and following counts.
      - Log the follow event and send email & notification.

    Returns:
      A success message.
    """
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

    # Check for mutual follow
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

    user_to_follow.followers_count += 1
    current_user.following_count += 1

    db.commit()
    log_user_event(db, current_user.id, "follow_user", {"followed_id": user_id})

    background_tasks.add_task(
        send_email_notification,
        to=user_to_follow.email,
        subject="New Follower",
        body=f"You have a new follower: {current_user.email}",
    )
    create_notification(
        db,
        user_id,
        f"{current_user.username} started following you",
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
    """
    Unfollow a user.

    Parameters:
      - user_id: ID of the user to unfollow.
      - background_tasks: Background tasks manager.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify that the follow record exists.
      - If it is a mutual follow, update the mutual flag on the other record.
      - Delete the follow record.
      - Update followers and following counts.
      - Send email notification.

    Returns:
      None.
    """
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
    user_unfollowed.followers_count -= 1
    current_user.following_count -= 1
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
    """
    Retrieve a list of followers for the current user.

    Parameters:
      - sort_by: Field to sort by ("date" or "username").
      - order: Sort order ("asc" or "desc").
      - skip: Number of records to skip.
      - limit: Maximum number of records to return.

    Returns:
      A dictionary containing the list of followers and total count.
    """
    query = db.query(models.Follow).filter(models.Follow.followed_id == current_user.id)
    if sort_by == "date":
        order_column = models.Follow.created_at
    elif sort_by == "username":
        order_column = models.User.username

    query = (
        query.order_by(desc(order_column))
        if order == "desc"
        else query.order_by(asc(order_column))
    )

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
    """
    Retrieve a list of users that the current user is following.

    Parameters:
      - sort_by: Field to sort by ("date" or "username").
      - order: Sort order ("asc" or "desc").
      - skip: Number of records to skip.
      - limit: Maximum number of records to return.

    Returns:
      A dictionary containing the list of following users and total count.
    """
    query = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id)
    if sort_by == "date":
        order_column = models.Follow.created_at
    elif sort_by == "username":
        order_column = models.User.username

    query = (
        query.order_by(desc(order_column))
        if order == "desc"
        else query.order_by(asc(order_column))
    )

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


@router.get("/statistics", response_model=schemas.FollowStatistics)
def get_follow_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve follow statistics for the current user.

    Process:
      - Calculate follower growth over the past 30 days.
      - Calculate the interaction rate based on posts and comments.

    Returns:
      A dictionary containing followers count, following count, daily growth, and interaction rate.
    """
    thirty_days_ago = datetime.now() - timedelta(days=30)
    daily_growth = (
        db.query(func.date(models.Follow.created_at), func.count())
        .filter(models.Follow.followed_id == current_user.id)
        .filter(models.Follow.created_at >= thirty_days_ago)
        .group_by(func.date(models.Follow.created_at))
        .all()
    )

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
    """
    Retrieve a list of mutual followers for the current user.

    Returns:
      A list of user objects representing mutual followers.
    """
    mutual_followers = (
        db.query(models.User)
        .join(models.Follow, models.User.id == models.Follow.follower_id)
        .filter(models.Follow.followed_id == current_user.id)
        .filter(models.Follow.is_mutual == True)
        .all()
    )
    return mutual_followers
