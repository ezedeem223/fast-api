from fastapi import APIRouter, status, Depends, BackgroundTasks, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import timedelta
from ..models import User
from .. import schemas, oauth2
from app.core.database import get_db
from app.services.comments import CommentService
from app.notifications import (
    queue_email_notification,
    schedule_email_notification,
)
from app.core.middleware.rate_limit import limiter
from app.core.cache.redis_cache import (
    cache,
    cache_manager,
)  # Task 5: Redis Caching Imports


router = APIRouter(prefix="/comments", tags=["Comments"])


def get_comment_service(db: Session = Depends(get_db)) -> CommentService:
    """Provide a CommentService instance for route handlers."""
    return CommentService(db)


# إذا لم يكن هناك حد زمني للتعديل، نترك EDIT_WINDOW فارغاً
EDIT_WINDOW: Optional[timedelta] = None


# API Endpoints


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommentOut
)
@limiter.limit("30/minute")
async def create_comment(
    request: Request,
    background_tasks: BackgroundTasks,
    comment: schemas.CommentCreate,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Create a new comment.

    Parameters:
      - request: HTTP request object (required for rate limiting).
      - comment: CommentCreate schema containing comment data.
      - background_tasks: For scheduling background tasks.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify user is verified.
      - Verify that the post exists.
      - Validate the comment content.
      - Create a new comment and update related counts.
      - Log the event and send notifications.
      - Update the post score.

    Returns:
      The newly created comment.
    """
    result = await service.create_comment(
        schema=comment,
        current_user=current_user,
        background_tasks=background_tasks,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
    )

    # Task 5: Invalidate comments cache when a new comment is added
    # Using a pattern to invalidate all sorted/paginated versions of the list
    await cache_manager.invalidate("comments:list:*")

    return result


@router.get("/{post_id}", response_model=List[schemas.CommentOut])
# Task 5: Add cache decorator (2 minutes TTL)
@cache(prefix="comments:list", ttl=120)
async def get_comments(
    post_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
    sort_by: Optional[str] = Query("created_at", enum=["created_at", "likes_count"]),
    sort_order: Optional[str] = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve comments for a post.

    Parameters:
      - post_id: ID of the post.
      - sort_by: Field to sort comments by.
      - sort_order: Sort order.
      - skip: Number of comments to skip.
      - limit: Maximum number of comments to return.

    Process:
      - Verify that the post exists.
      - Apply sorting.
      - Filter out flagged comments for non-moderators.
      - Translate comment content.

    Returns:
      A list of comments.
    """
    return await service.list_comments(
        post_id=post_id,
        current_user=current_user,
        sort_by=sort_by or "created_at",
        sort_order=sort_order or "desc",
        skip=skip,
        limit=limit,
    )


@router.get("/{comment_id}/replies", response_model=List[schemas.CommentOut])
def get_comment_replies(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
    sort_by: Optional[str] = Query("created_at", enum=["created_at", "likes_count"]),
    sort_order: Optional[str] = Query("desc", enum=["asc", "desc"]),
):
    """
    Retrieve replies for a specific comment.

    Parameters:
      - comment_id: ID of the parent comment.
      - sort_by: Field to sort by.
      - sort_order: Sort order.

    Returns:
      A list of replies.
    """
    return service.list_replies(
        comment_id=comment_id,
        current_user=current_user,
        sort_by=sort_by or "created_at",
        sort_order=sort_order or "desc",
    )


@router.put("/{comment_id}", response_model=schemas.Comment)
@limiter.limit("20/hour")
def update_comment(
    request: Request,
    comment_id: int,
    updated_comment: schemas.CommentUpdate,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Update an existing comment.

    Parameters:
      - request: HTTP request object (required for rate limiting).
      - comment_id: ID of the comment to update.
      - updated_comment: New content for the comment.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify comment existence.
      - Check ownership and edit window.
      - Save previous content to edit history.
      - Update the comment and mark it as edited.

    Returns:
      The updated comment.
    """
    return service.update_comment(
        comment_id=comment_id,
        payload=updated_comment,
        current_user=current_user,
        edit_window=EDIT_WINDOW,
    )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Soft delete a comment.

    Parameters:
      - comment_id: ID of the comment to delete.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify comment existence and ownership.
      - Mark the comment as deleted and update deletion timestamp.

    Returns:
      A confirmation message.
    """
    return service.delete_comment(comment_id=comment_id, current_user=current_user)


@router.get("/{comment_id}/history", response_model=List[schemas.CommentEditHistoryOut])
def get_comment_edit_history(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Retrieve the edit history for a specific comment.

    Parameters:
      - comment_id: ID of the comment.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      A list of edit history records for the comment.

    Raises:
      HTTPException: If the comment is not found or if access is unauthorized.
    """
    return service.get_edit_history(
        comment_id=comment_id,
        current_user=current_user,
    )


@router.post(
    "/report", status_code=status.HTTP_201_CREATED, response_model=schemas.Report
)
@limiter.limit("5/hour")
def report_comment(
    request: Request,
    report: schemas.ReportCreate,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """Report a post or comment."""
    return service.report_content(payload=report, current_user=current_user)


@router.post("/{comment_id}/like", status_code=status.HTTP_200_OK)
@limiter.limit("60/minute")
def like_comment(
    request: Request,
    comment_id: int,
    service: CommentService = Depends(get_comment_service),
):
    """
    Like a comment.

    Parameters:
      - request: HTTP request object (required for rate limiting).
      - comment_id: ID of the comment to like.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      A confirmation message.
    """
    return service.like_comment(comment_id=comment_id)


@router.put("/{comment_id}/highlight", response_model=schemas.CommentOut)
def highlight_comment(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Toggle the highlighted status of a comment.

    Parameters:
      - comment_id: ID of the comment to highlight.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.
    """
    return service.toggle_highlight(comment_id=comment_id, current_user=current_user)


@router.put("/{comment_id}/best-answer", response_model=schemas.CommentOut)
def set_best_answer(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Set a comment as the best answer for a post.

    Parameters:
      - comment_id: ID of the comment to mark as best answer.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.
    """
    return service.set_best_answer(comment_id=comment_id, current_user=current_user)


@router.put("/{comment_id}/pin", response_model=schemas.CommentOut)
def pin_comment(
    comment_id: int,
    current_user: User = Depends(oauth2.get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    """
    Pin or unpin a comment on a post.

    Parameters:
      - comment_id: ID of the comment to pin.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.

    Raises:
      HTTPException: If maximum number of pinned comments is reached.
    """
    return service.toggle_pin(comment_id=comment_id, current_user=current_user)
