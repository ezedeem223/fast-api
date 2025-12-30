"""Hashtag router for CRUD, analytics, and popularity calculations."""

from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, status

from .. import models, oauth2, schemas

router = APIRouter(prefix="/hashtags", tags=["Hashtags"])

# CRUD Operations


@router.post("/", response_model=schemas.Hashtag)
def create_hashtag(hashtag: schemas.HashtagCreate, db: Session = Depends(get_db)):
    """
    Create a new hashtag.

    Parameters:
      - hashtag: HashtagCreate schema with the hashtag data.
      - db: Database session.

    Returns:
      The newly created hashtag.
    """
    db_hashtag = models.Hashtag(name=hashtag.name)
    db.add(db_hashtag)
    db.commit()
    db.refresh(db_hashtag)
    return db_hashtag


@router.get("/", response_model=List[schemas.Hashtag])
def get_hashtags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of hashtags.

    Parameters:
      - skip: Number of items to skip.
      - limit: Maximum number of items to return.
      - db: Database session.

    Returns:
      A list of hashtags.
    """
    hashtags = db.query(models.Hashtag).offset(skip).limit(limit).all()
    return hashtags


# Follow/Unfollow Operations


@router.post("/follow/{hashtag_id}")
def follow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Follow a specific hashtag.

    Parameters:
      - hashtag_id: The ID of the hashtag.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      A confirmation message upon success.
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )
    if hashtag in current_user.followed_hashtags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following this hashtag",
        )
    current_user.followed_hashtags.append(hashtag)
    db.commit()
    return {"message": "Hashtag followed successfully"}


@router.post("/unfollow/{hashtag_id}")
def unfollow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Unfollow a specific hashtag.

    Parameters:
      - hashtag_id: The ID of the hashtag.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      A confirmation message upon success.
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )
    if hashtag not in current_user.followed_hashtags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Not following this hashtag"
        )
    current_user.followed_hashtags.remove(hashtag)
    db.commit()
    return {"message": "Hashtag unfollowed successfully"}


# Analytics and Trending


@router.get("/trending", response_model=List[schemas.Hashtag])
def get_trending_hashtags(db: Session = Depends(get_db), limit: int = 10):
    """
    Retrieve the most popular hashtags.

    Parameters:
      - db: Database session.
      - limit: Maximum number of results.

    Returns:
      A list of the most used hashtags.
    """
    trending_hashtags = (
        db.query(models.Hashtag)
        .join(models.Post.hashtags)
        .group_by(models.Hashtag.id)
        .order_by(func.count(models.Post.id).desc())
        .limit(limit)
        .all()
    )
    return trending_hashtags


@router.get("/{hashtag_name}/posts", response_model=List[schemas.PostOut])
def get_posts_by_hashtag(
    hashtag_name: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 100
):
    """
    Retrieve posts associated with a specific hashtag.

    Parameters:
      - hashtag_name: The name of the hashtag.
      - db: Database session.
      - skip: Number of items to skip.
      - limit: Maximum number of results.

    Returns:
      A list of posts associated with the hashtag.
    """
    posts = (
        db.query(models.Post)
        .join(models.Post.hashtags)
        .filter(models.Hashtag.name == hashtag_name)
        .offset(skip)
        .limit(limit)
        .all()
    )
    if not posts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No posts found with hashtag: {hashtag_name}",
        )
    return posts


# Statistics and Analytics


@router.get("/{hashtag_id}/statistics", response_model=schemas.HashtagStatistics)
def get_hashtag_statistics(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve statistics for a specific hashtag.

    Parameters:
      - hashtag_id: The ID of the hashtag.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      Hashtag statistics.
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )
    post_count = (
        db.query(func.count(models.Post.id))
        .join(models.Post.hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )
    follower_count = (
        db.query(func.count(models.User.id))
        .join(models.User.followed_hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )
    engagement_rate = calculate_engagement_rate(db, hashtag_id)
    return schemas.HashtagStatistics(
        post_count=post_count,
        follower_count=follower_count,
        engagement_rate=engagement_rate,
    )


def calculate_engagement_rate(db: Session, hashtag_id: int) -> float:
    """
    Calculate the engagement rate for a hashtag.

    Parameters:
      - db: Database session.
      - hashtag_id: The ID of the hashtag.

    Returns:
      The engagement rate.
    """
    total_interactions = (
        db.query(func.count(models.Vote.id) + func.count(models.Comment.id))
        .join(models.Post.hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )
    post_count = (
        db.query(func.count(models.Post.id))
        .join(models.Post.hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )
    if post_count == 0:
        return 0.0
    return total_interactions / post_count
