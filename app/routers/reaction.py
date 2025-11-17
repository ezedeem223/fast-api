from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from .. import models, schemas, oauth2
from app.core.database import get_db

router = APIRouter(prefix="/reactions", tags=["Reactions"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Reaction)
def create_reaction(
    reaction: schemas.ReactionCreate,
    post_id: int = None,
    comment_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create or update a reaction on a post or comment.

    Either post_id or comment_id must be provided (but not both).

    If a reaction by the current user already exists with the same reaction_type,
    the reaction will be removed. If it exists with a different reaction_type,
    it will be updated accordingly.

    Args:
        reaction (schemas.ReactionCreate): Reaction data containing reaction_type.
        post_id (int, optional): ID of the post to react to.
        comment_id (int, optional): ID of the comment to react to.
        db (Session): Database session.
        current_user (models.User): The authenticated user.

    Returns:
        Union[dict, models.Reaction]: A success message when reaction is removed,
                                      or the created/updated Reaction object.

    Raises:
        HTTPException: If neither or both of post_id and comment_id are provided,
                       or if the target post/comment does not exist.
    """
    if post_id is None and comment_id is None:
        raise HTTPException(
            status_code=400, detail="Either post_id or comment_id must be provided"
        )

    if post_id and comment_id:
        raise HTTPException(
            status_code=400,
            detail="Only one of post_id or comment_id should be provided",
        )

    # Check if the target post or comment exists
    if post_id:
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
    else:
        comment = (
            db.query(models.Comment).filter(models.Comment.id == comment_id).first()
        )
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

    # Check for an existing reaction by the user for the same target
    existing_reaction = (
        db.query(models.Reaction)
        .filter(
            models.Reaction.user_id == current_user.id,
            (
                (models.Reaction.post_id == post_id)
                if post_id
                else (models.Reaction.comment_id == comment_id)
            ),
        )
        .first()
    )

    if existing_reaction:
        if existing_reaction.reaction_type == reaction.reaction_type:
            # If the same reaction exists, remove it
            db.delete(existing_reaction)
            db.commit()
            return {"message": "Reaction removed"}
        else:
            # If a different reaction exists, update its type
            existing_reaction.reaction_type = reaction.reaction_type
            db.commit()
            db.refresh(existing_reaction)
            return existing_reaction

    # Create a new reaction
    new_reaction = models.Reaction(
        user_id=current_user.id,
        post_id=post_id,
        comment_id=comment_id,
        reaction_type=reaction.reaction_type,
    )
    db.add(new_reaction)
    db.commit()
    db.refresh(new_reaction)
    return new_reaction


@router.get("/post/{post_id}", response_model=List[schemas.ReactionCount])
def get_post_reaction_counts(post_id: int, db: Session = Depends(get_db)):
    """
    Retrieve the count of reactions for a specific post grouped by reaction type.

    Args:
        post_id (int): ID of the post.
        db (Session): Database session.

    Returns:
        List[dict]: A list of dictionaries containing reaction_type and its count.
    """
    reactions = (
        db.query(
            models.Reaction.reaction_type, func.count(models.Reaction.id).label("count")
        )
        .filter(models.Reaction.post_id == post_id)
        .group_by(models.Reaction.reaction_type)
        .all()
    )

    return [{"reaction_type": r.reaction_type, "count": r.count} for r in reactions]


@router.get("/comment/{comment_id}", response_model=List[schemas.ReactionCount])
def get_comment_reaction_counts(comment_id: int, db: Session = Depends(get_db)):
    """
    Retrieve the count of reactions for a specific comment grouped by reaction type.

    Args:
        comment_id (int): ID of the comment.
        db (Session): Database session.

    Returns:
        List[dict]: A list of dictionaries containing reaction_type and its count.
    """
    reactions = (
        db.query(
            models.Reaction.reaction_type, func.count(models.Reaction.id).label("count")
        )
        .filter(models.Reaction.comment_id == comment_id)
        .group_by(models.Reaction.reaction_type)
        .all()
    )

    return [{"reaction_type": r.reaction_type, "count": r.count} for r in reactions]
