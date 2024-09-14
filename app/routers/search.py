from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, database, schemas

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/", response_model=List[schemas.PostOut])
def search_posts(query: Optional[str] = "", db: Session = Depends(database.get_db)):
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")

    # تحسين الاستعلام بإضافة تصفية أو ترتيب إذا لزم الأمر
    posts = db.query(models.Post).filter(models.Post.content.contains(query)).all()

    if not posts:
        raise HTTPException(
            status_code=404, detail="No posts found matching the query."
        )

    return posts
