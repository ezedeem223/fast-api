from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import models, database, schemas

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/", response_model=List[schemas.PostOut])
def search_posts(query: str, db: Session = Depends(database.get_db)):
    posts = db.query(models.Post).filter(models.Post.content.contains(query)).all()
    return posts
