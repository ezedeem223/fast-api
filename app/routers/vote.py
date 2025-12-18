"""Vote router for post voting and side-effect hooks."""

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status, Request


from .. import oauth2, schemas
from app.core.database import get_db
from app.modules.posts import VoteService
from app.modules.users.models import User
from sqlalchemy.orm import Session
from ..notifications import queue_email_notification, schedule_email_notification
from app.notifications import create_notification
from app import notifications
from app.core.middleware.rate_limit import limiter


router = APIRouter(prefix="/vote", tags=["Vote"])


def get_vote_service(db: Session = Depends(get_db)) -> VoteService:
    """Provide a VoteService instance via FastAPI dependency injection."""
    return VoteService(db)


@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def vote(
    request: Request,
    vote: schemas.ReactionCreate,
    background_tasks: BackgroundTasks,
    service: VoteService = Depends(get_vote_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Create or update a reaction on a post."""
    return service.vote(
        payload=vote,
        current_user=current_user,
        background_tasks=background_tasks,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        create_notification_fn=create_notification,
        notification_manager=notifications.manager,
    )


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reaction(
    post_id: int,
    background_tasks: BackgroundTasks,
    service: VoteService = Depends(get_vote_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Remove a reaction from a post."""
    service.remove_reaction(
        post_id=post_id,
        current_user=current_user,
        background_tasks=background_tasks,
        queue_email_fn=queue_email_notification,
        create_notification_fn=create_notification,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{post_id}")
def get_vote_count(
    post_id: int,
    service: VoteService = Depends(get_vote_service),
):
    """Get the vote count for a given post."""
    return service.get_vote_count(post_id=post_id)


@router.get("/{post_id}/voters", response_model=schemas.VotersListOut)
def get_post_voters(
    post_id: int,
    service: VoteService = Depends(get_vote_service),
    current_user: User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 50,
):
    """Retrieve the list of users who voted on the post."""
    return service.get_post_voters(
        post_id=post_id,
        current_user=current_user,
        skip=skip,
        limit=limit,
    )
