from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, database, schemas, oauth2
from ..database import get_db
from sqlalchemy import or_, and_
from ..config import redis_client
import json


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


@router.get("/advanced", response_model=List[schemas.PostOut])
async def advanced_search(
    query: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    category_id: Optional[int] = None,
    author_id: Optional[int] = None,
    search_scope: Optional[str] = Query(
        None, enum=["title", "content", "comments", "all"]
    ),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 20,
):
    search_query = db.query(models.Post)

    if query:
        if search_scope == "title" or search_scope == "all":
            search_query = search_query.filter(models.Post.title.ilike(f"%{query}%"))
        elif search_scope == "content" or search_scope == "all":
            search_query = search_query.filter(models.Post.content.ilike(f"%{query}%"))
        elif search_scope == "comments":
            search_query = search_query.join(models.Comment).filter(
                models.Comment.content.ilike(f"%{query}%")
            )

    if start_date:
        search_query = search_query.filter(models.Post.created_at >= start_date)
    if end_date:
        search_query = search_query.filter(models.Post.created_at <= end_date)
    if category_id:
        search_query = search_query.filter(models.Post.category_id == category_id)
    if author_id:
        search_query = search_query.filter(models.Post.owner_id == author_id)

    total = search_query.count()
    posts = (
        search_query.order_by(models.Post.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {"total": total, "posts": [schemas.PostOut.from_orm(post) for post in posts]}


@router.get("/categories", response_model=List[schemas.Category])
async def get_categories(db: Session = Depends(database.get_db)):
    categories = db.query(models.Category).all()
    return categories


@router.get("/authors", response_model=List[schemas.UserOut])
async def get_authors(db: Session = Depends(database.get_db)):
    authors = db.query(models.User).filter(models.User.post_count > 0).all()
    return authors


@router.get("/autocomplete", response_model=List[schemas.SearchSuggestionOut])
async def autocomplete(
    query: str = Query(..., min_length=1),
    db: Session = Depends(database.get_db),
    limit: int = 10,
):
    # محاولة الحصول على النتائج من Redis أولاً
    cache_key = f"autocomplete:{query}"
    cached_result = redis_client.get(cache_key)
    if cached_result:
        return json.loads(cached_result)

    suggestions = (
        db.query(models.SearchSuggestion)
        .filter(models.SearchSuggestion.term.ilike(f"{query}%"))
        .order_by(models.SearchSuggestion.frequency.desc())
        .limit(limit)
        .all()
    )

    result = [schemas.SearchSuggestionOut.from_orm(s) for s in suggestions]

    # تخزين النتيجة في Redis لمدة 5 دقائق
    redis_client.setex(cache_key, 300, json.dumps([s.dict() for s in result]))

    return result


@router.post("/record-search")
async def record_search(
    term: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    suggestion = (
        db.query(models.SearchSuggestion)
        .filter(models.SearchSuggestion.term == term)
        .first()
    )
    if suggestion:
        suggestion.frequency += 1
    else:
        suggestion = models.SearchSuggestion(term=term)
        db.add(suggestion)
    db.commit()
    return {"status": "recorded"}


# دالة مساعدة لتحديث اقتراحات البحث بناءً على محتوى المنشورات
def update_search_suggestions(db: Session):
    posts = db.query(models.Post).all()
    for post in posts:
        words = set(post.title.split() + post.content.split())
        for word in words:
            if len(word) > 2:  # تجاهل الكلمات القصيرة جدًا
                suggestion = (
                    db.query(models.SearchSuggestion)
                    .filter(models.SearchSuggestion.term == word)
                    .first()
                )
                if suggestion:
                    suggestion.frequency += 1
                else:
                    suggestion = models.SearchSuggestion(term=word)
                    db.add(suggestion)
    db.commit()
