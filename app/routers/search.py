from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from .. import models, database, schemas, oauth2
from ..database import get_db
from sqlalchemy import or_, and_
from ..config import redis_client
import json
from ..utils import (
    search_posts,
    get_spell_suggestions,
    format_spell_suggestions,
    sort_search_results,
    analyze_user_behavior,
)
from ..schemas import SearchParams, SearchResponse, SortOption
from ..analytics import (
    record_search_query,
    get_popular_searches,
    get_recent_searches,
    get_user_searches,
    generate_search_trends_chart,
)
from ..utils import analyze_user_behavior


router = APIRouter(prefix="/search", tags=["Search"])


@router.post("/", response_model=SearchResponse)
async def search(
    search_params: SearchParams,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    cache_key = f"search:{search_params.query}:{search_params.sort_by}"
    cached_result = redis_client.get(cache_key)

    if cached_result:
        return json.loads(cached_result)

    # Record search query
    record_search_query(db, search_params.query, current_user.id)

    suggestions = get_spell_suggestions(search_params.query)
    spell_suggestion = format_spell_suggestions(search_params.query, suggestions)

    results = search_posts(search_params.query, db)
    sorted_results = sort_search_results(results, search_params.sort_by, db)

    # Get search suggestions
    popular_searches = get_popular_searches(db, limit=3)
    user_searches = get_user_searches(db, current_user.id, limit=2)
    search_suggestions = list(
        set([stat.query for stat in popular_searches + user_searches])
    )

    search_response = {
        "results": sorted_results,
        "spell_suggestion": spell_suggestion,
        "search_suggestions": search_suggestions,
    }

    if results:
        redis_client.setex(cache_key, 3600, json.dumps(search_response))

    return search_response


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
    db: Session = Depends(get_db),
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
async def get_categories(db: Session = Depends(get_db)):
    categories = db.query(models.Category).all()
    return categories


@router.get("/authors", response_model=List[schemas.UserOut])
async def get_authors(db: Session = Depends(get_db)):
    authors = db.query(models.User).filter(models.User.post_count > 0).all()
    return authors


@router.get("/autocomplete", response_model=List[schemas.SearchSuggestionOut])
async def autocomplete(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    limit: int = 10,
):
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

    redis_client.setex(cache_key, 300, json.dumps([s.dict() for s in result]))

    return result


@router.post("/record-search")
async def record_search(
    term: str,
    db: Session = Depends(get_db),
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


@router.get("/popular", response_model=List[schemas.SearchStatOut])
async def popular_searches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
    limit: int = Query(10, ge=1, le=100),
):
    return get_popular_searches(db, limit)


@router.get("/recent", response_model=List[schemas.SearchStatOut])
async def recent_searches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
    limit: int = Query(10, ge=1, le=100),
):
    return get_recent_searches(db, limit)


@router.get("/trends")
async def search_trends(current_user: models.User = Depends(oauth2.get_current_admin)):
    chart = generate_search_trends_chart()
    return {"chart": chart}


def update_search_suggestions(db: Session):
    posts = db.query(models.Post).all()
    for post in posts:
        words = set(post.title.split() + post.content.split())
        for word in words:
            if len(word) > 2:
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


@router.get("/smart", response_model=List[schemas.PostOut])
async def smart_search(
    query: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    # الحصول على تاريخ بحث المستخدم
    user_history = (
        db.query(models.SearchStatistics.query)
        .filter(models.SearchStatistics.user_id == current_user.id)
        .order_by(models.SearchStatistics.last_searched.desc())
        .limit(20)
        .all()
    )
    user_history = [item[0] for item in user_history]

    # البحث الأولي
    search_query = func.plainto_tsquery("english", query)
    initial_results = (
        db.query(models.Post)
        .filter(models.Post.search_vector.op("@@")(search_query))
        .all()
    )

    # تطبيق الفلترة الذكية
    scored_results = [
        (post, analyze_user_behavior(user_history, post.content))
        for post in initial_results
    ]
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # تحديث إحصائيات البحث
    update_search_statistics(db, current_user.id, query)

    return [
        schemas.PostOut.from_orm(post)
        for post, _ in scored_results[skip : skip + limit]
    ]


def update_search_statistics(db: Session, user_id: int, query: str):
    stat = (
        db.query(models.SearchStatistics)
        .filter(
            models.SearchStatistics.user_id == user_id,
            models.SearchStatistics.query == query,
        )
        .first()
    )

    if stat:
        stat.count += 1
        stat.last_searched = func.now()
    else:
        new_stat = models.SearchStatistics(user_id=user_id, query=query)
        db.add(new_stat)

    db.commit()
