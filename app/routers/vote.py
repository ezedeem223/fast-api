from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from .. import models, schemas, oauth2
from ..database import get_db
from ..notifications import schedule_email_notification
from ..utils import (
    update_post_score,
    update_post_vote_statistics,
    get_user_vote_analytics,
    create_notification,
)

router = APIRouter(prefix="/vote", tags=["Vote"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def vote(
    vote: schemas.ReactionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إنشاء أو تحديث تفاعل (reaction) على المنشور.
    Create or update a reaction on a post.
    """
    # Validate vote direction: must be either 0 or 1.
    if vote.dir not in [0, 1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vote direction. Must be 0 or 1.",
        )

    # Retrieve the post by ID.
    post = db.query(models.Post).filter(models.Post.id == vote.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {vote.post_id} does not exist",
        )

    # Check if the user already has a reaction on the post.
    existing_reaction = (
        db.query(models.Reaction)
        .filter(
            models.Reaction.post_id == vote.post_id,
            models.Reaction.user_id == current_user.id,
        )
        .first()
    )

    if existing_reaction:
        if existing_reaction.reaction_type == vote.reaction_type:
            # If the same reaction exists, remove it.
            db.delete(existing_reaction)
            db.commit()
            message = f"Successfully removed {vote.reaction_type} reaction"
        else:
            # If a different reaction exists, update it.
            existing_reaction.reaction_type = vote.reaction_type
            db.commit()
            message = f"Successfully updated reaction to {vote.reaction_type}"
    else:
        # Create a new reaction.
        new_reaction = models.Reaction(
            user_id=current_user.id,
            post_id=vote.post_id,
            reaction_type=vote.reaction_type,
        )
        db.add(new_reaction)
        db.commit()
        message = f"Successfully added {vote.reaction_type} reaction"

    # Update the post's score based on reactions, comment count, and age.
    update_post_score(db, post)

    # Determine the action for the email notification.
    reaction_action = "added to" if not existing_reaction else "updated on"
    background_tasks.add_task(
        schedule_email_notification,
        to=post.owner.email,
        subject="Reaction Activity on Your Post",
        body=f"A {vote.reaction_type} reaction has been {reaction_action} your post by user {current_user.id}",
    )

    # Create an internal notification for the post owner.
    create_notification(
        db,
        post.owner_id,
        f"{current_user.username} отреагировал на ваш пост: {vote.reaction_type}",
        f"/post/{post.id}",
        "new_reaction",
        post.id,
    )

    # Update post vote statistics asynchronously.
    background_tasks.add_task(update_post_vote_statistics, db, vote.post_id)

    return {"message": message}


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reaction(
    post_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إزالة تفاعل (reaction) من المنشور.
    Remove a reaction from a post.
    """
    # Find the reaction for the given post and user.
    reaction_query = db.query(models.Reaction).filter(
        models.Reaction.post_id == post_id, models.Reaction.user_id == current_user.id
    )
    reaction = reaction_query.first()

    if not reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reaction not found"
        )

    # Delete the reaction.
    reaction_query.delete(synchronize_session=False)
    db.commit()

    # Retrieve the post and update its score.
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    update_post_score(db, post)

    # Schedule an email notification to inform the post owner.
    background_tasks.add_task(
        schedule_email_notification,
        to=post.owner.email,
        subject="Reaction Removed from Your Post",
        body=f"A reaction has been removed from your post by user {current_user.id}",
    )

    # Create an internal notification for the post owner.
    create_notification(
        db,
        post.owner_id,
        f"{current_user.username} удалил реакцию с вашего поста",
        f"/post/{post.id}",
        "removed_reaction",
        post.id,
    )

    # Update post vote statistics asynchronously.
    background_tasks.add_task(update_post_vote_statistics, db, post_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{post_id}")
def get_vote_count(post_id: int, db: Session = Depends(get_db)):
    """
    الحصول على عدد الأصوات على المنشور.
    Get the vote count for a given post.
    """
    votes = db.query(models.Vote).filter(models.Vote.post_id == post_id).count()
    return {"post_id": post_id, "votes": votes}


@router.get("/{post_id}/voters", response_model=schemas.VotersListOut)
def get_post_voters(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 50,
):
    """
    الحصول على قائمة المستخدمين الذين قاموا بالتصويت على المنشور.
    Retrieve the list of users who voted on the post.
    """
    # Verify that the post exists.
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Check access rights: only the post owner or moderators can view the voters list.
    if post.owner_id != current_user.id and not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized to view voters")

    # Retrieve voters through joining the Vote and User models.
    voters_query = (
        db.query(models.User).join(models.Vote).filter(models.Vote.post_id == post_id)
    )
    total_count = voters_query.count()
    voters = voters_query.offset(skip).limit(limit).all()

    return schemas.VotersListOut(
        voters=[schemas.VoterOut.from_orm(voter) for voter in voters],
        total_count=total_count,
    )


# --- Helper Function ---


def update_post_score(db: Session, post: models.Post):
    """
    تحديث درجة المنشور استناداً إلى التفاعلات، عدد التعليقات، وعمر المنشور.
    Update the post's score based on its reactions, comment count, and age.
    """
    reactions = (
        db.query(models.Reaction).filter(models.Reaction.post_id == post.id).all()
    )

    # Define weights for each reaction type.
    reaction_weights = {
        "like": 1,
        "love": 2,
        "haha": 1.5,
        "wow": 1.5,
        "sad": 1,
        "angry": 1,
    }

    # Calculate score as the sum of weighted reactions.
    score = sum(
        reaction_weights.get(reaction.reaction_type, 1) for reaction in reactions
    )

    # Add influence of comment count.
    score += post.comment_count * 0.5

    # Adjust score based on post age (newer posts get a boost).
    age_hours = (datetime.now(timezone.utc) - post.created_at).total_seconds() / 3600.0
    score = score / (age_hours + 2) ** 1.8

    post.score = score
    db.commit()
