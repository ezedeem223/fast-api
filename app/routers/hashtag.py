from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/hashtags", tags=["Hashtags"])


@router.post("/", response_model=schemas.Hashtag)
def create_hashtag(hashtag: schemas.HashtagCreate, db: Session = Depends(get_db)):
    db_hashtag = models.Hashtag(name=hashtag.name)
    db.add(db_hashtag)
    db.commit()
    db.refresh(db_hashtag)
    return db_hashtag


@router.get("/", response_model=List[schemas.Hashtag])
def get_hashtags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    hashtags = db.query(models.Hashtag).offset(skip).limit(limit).all()
    return hashtags


@router.post("/follow/{hashtag_id}")
def follow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(status_code=404, detail="Hashtag not found")
    current_user.followed_hashtags.append(hashtag)
    db.commit()
    return {"message": "Hashtag followed successfully"}


@router.post("/unfollow/{hashtag_id}")
def unfollow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(status_code=404, detail="Hashtag not found")
    current_user.followed_hashtags.remove(hashtag)
    db.commit()
    return {"message": "Hashtag unfollowed successfully"}


@router.get("/trending", response_model=List[schemas.Hashtag])
def get_trending_hashtags(db: Session = Depends(get_db), limit: int = 10):
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
def get_posts_by_hashtag(hashtag_name: str, db: Session = Depends(get_db)):
    posts = (
        db.query(models.Post)
        .join(models.Post.hashtags)
        .filter(models.Hashtag.name == hashtag_name)
        .all()
    )
    return posts
