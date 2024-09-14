from fastapi import (
    APIRouter,
    Response,
    status,
    HTTPException,
    Depends,
    BackgroundTasks,
)
from sqlalchemy.orm import Session
from .. import schemas, database, models, oauth2, notifications

router = APIRouter(prefix="/vote", tags=["Vote"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def vote(
    vote: schemas.Vote,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    # Check if the post exists
    post = db.query(models.Post).filter(models.Post.id == vote.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {vote.post_id} does not exist",
        )

    # Query for an existing vote
    vote_query = db.query(models.Vote).filter(
        models.Vote.post_id == vote.post_id, models.Vote.user_id == current_user.id
    )
    found_vote = vote_query.first()

    if vote.dir == 1:
        if found_vote:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User {current_user.id} has already voted on post {vote.post_id}",
            )
        # Create a new vote
        new_vote = models.Vote(post_id=vote.post_id, user_id=current_user.id)
        db.add(new_vote)
        db.commit()

        # Send notification for new vote
        notifications.schedule_email_notification(
            background_tasks,
            to=post.owner.email,  # Changed from list to single email
            subject="New Vote on Your Post",
            body=f"User {current_user.id} voted on your post.",
        )

        return {"message": "Successfully added vote"}
    else:
        if not found_vote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Vote does not exist"
            )
        # Remove the vote
        vote_query.delete(synchronize_session=False)
        db.commit()

        # Send notification for vote removal
        notifications.schedule_email_notification(
            background_tasks,
            to=post.owner.email,  # Changed from list to single email
            subject="Vote Removed from Your Post",
            body=f"User {current_user.id} removed their vote from your post.",
        )

        return {"message": "Successfully deleted vote"}
