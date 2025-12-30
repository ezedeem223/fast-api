"""Follow router for follow/unfollow flows and follower listings."""

from typing import List

from sqlalchemy.orm import Session

from app import notifications
from app.core.cache.redis_cache import cache  # Task 5: Redis Caching Imports
from app.core.cache.redis_cache import (
    cache_manager,
)
from app.core.database import get_db
from app.core.middleware.rate_limit import limiter
from app.modules.social import FollowService
from app.modules.users.models import User
from app.notifications import create_notification
from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request, status

from .. import oauth2, schemas
from ..notifications import queue_email_notification, schedule_email_notification

router = APIRouter(prefix="/follow", tags=["Follow"])


def get_follow_service(db: Session = Depends(get_db)) -> FollowService:
    """Provide a FollowService instance via FastAPI DI."""
    return FollowService(db)


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def follow_user(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: int = Path(..., gt=0),
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """
    Follow a user.

    Parameters:
      - request: HTTP request object (required for rate limiting).
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
    result = service.follow_user(
        background_tasks=background_tasks,
        current_user=current_user,
        target_user_id=user_id,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        notification_manager=notifications.manager,
        create_notification_fn=create_notification,
    )

    # Task 5: Invalidate cache for current user's following list
    # The cache key includes user ID because include_user=True in decorator
    await cache_manager.invalidate(f"users:following:u{current_user.id}:*")
    # Optionally also invalidate followers cache for target user (if we had access to it here)
    # For simplicity, we invalidate the current user's following only

    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    background_tasks: BackgroundTasks,
    user_id: int = Path(..., gt=0),
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
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
    result = service.unfollow_user(
        background_tasks=background_tasks,
        current_user=current_user,
        target_user_id=user_id,
        queue_email_fn=queue_email_notification,
    )

    # Task 5: Invalidate cache when unfollowing
    await cache_manager.invalidate(f"users:following:u{current_user.id}:*")

    return result


@router.get("/followers", response_model=schemas.FollowersListOut)
# Task 5: Updated cache decorator with new syntax
@cache(prefix="users:followers", ttl=300, include_user=True)
async def get_followers(
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
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
    return service.get_followers(
        current_user=current_user,
        sort_by=sort_by,
        order=order,
        skip=skip,
        limit=limit,
    )


@router.get("/following", response_model=schemas.FollowingListOut)
# Task 5: Updated cache decorator with new syntax
@cache(prefix="users:following", ttl=300, include_user=True)
async def get_following(
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
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
    return service.get_following(
        current_user=current_user,
        sort_by=sort_by,
        order=order,
        skip=skip,
        limit=limit,
    )


@router.get("/statistics", response_model=schemas.FollowStatistics)
def get_follow_statistics(
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """
    Retrieve follow statistics for the current user.

    Process:
      - Calculate follower growth over the past 30 days.
      - Calculate the interaction rate based on posts and comments.

    Returns:
      A dictionary containing followers count, following count, daily growth, and interaction rate.
    """
    return service.get_follow_statistics(current_user=current_user)


@router.get("/mutual", response_model=List[schemas.UserOut])
def get_mutual_followers(
    service: FollowService = Depends(get_follow_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """
    Retrieve a list of mutual followers for the current user.

    Returns:
      A list of user objects representing mutual followers.
    """
    return service.get_mutual_followers(current_user=current_user)
