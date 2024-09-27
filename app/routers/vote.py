from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from ..notifications import schedule_email_notification

router = APIRouter(prefix="/vote", tags=["Vote"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def vote(
    vote: schemas.Vote,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    # Validate vote direction
    if vote.dir not in [0, 1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vote direction. Must be 0 or 1.",
        )

    post = db.query(models.Post).filter(models.Post.id == vote.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {vote.post_id} does not exist",
        )

    vote_query = db.query(models.Vote).filter(
        models.Vote.post_id == vote.post_id, models.Vote.user_id == current_user.id
    )
    found_vote = vote_query.first()

    if vote.dir == 1:
        if found_vote:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"user {current_user.id} has already voted on post {vote.post_id}",
            )
        new_vote = models.Vote(post_id=vote.post_id, user_id=current_user.id)
        db.add(new_vote)
        db.commit()
        message = "Successfully added vote"
    else:
        if not found_vote:
            message = "Vote doesn't exist, no action needed"
        else:
            vote_query.delete(synchronize_session=False)
            db.commit()
            message = "Successfully deleted vote"

    # Schedule email notification for both adding and removing votes
    schedule_email_notification(
        background_tasks,
        to=post.owner.email,
        subject="Vote Activity on Your Post",
        body=f"A vote has been {'added to' if vote.dir == 1 else 'removed from'} your post by user {current_user.id}",
    )

    return {"message": message}


# If you have any other routes in this file, they would go here.
# For example, you might have a route to get vote counts:


@router.get("/{post_id}")
def get_vote_count(post_id: int, db: Session = Depends(get_db)):
    votes = db.query(models.Vote).filter(models.Vote.post_id == post_id).count()
    return {"post_id": post_id, "votes": votes}


# Add any other vote-related routes here
