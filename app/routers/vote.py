from fastapi import (
    FastAPI,
    responses,
    Response,
    status,
    HTTPException,
    Depends,
    APIRouter,
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
    current_user: int = Depends(oauth2.get_current_user),
):
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

        # Sending a notification for a new vote
        background_tasks.add_task(
            notifications.send_email_notification,  # Changed from send_notification to send_email_notification
            f"User {current_user.id} voted on your post",
            post.owner_id,
        )

        return {"message": "successfully added vote"}
    else:
        if not found_vote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Vote does not exist"
            )
        vote_query.delete(synchronize_session=False)
        db.commit()

        # Sending a notification for vote deletion
        background_tasks.add_task(
            notifications.send_email_notification,  # Changed from send_notification to send_email_notification
            f"User {current_user.id} removed their vote from your post",
            post.owner_id,
        )

        return {"message": "successfully deleted vote"}
