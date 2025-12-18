"""Search router covering plain and advanced search with spell suggestions and cache integration."""

import os
import json
import logging
from datetime import datetime
from typing import List, Optional

from redis.exceptions import RedisError

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas, oauth2
from app.core.config import settings
from app.core.database import get_db
from app.modules.utils.search import (
    search_posts,
    get_spell_suggestions,
    format_spell_suggestions,
    sort_search_results,
)
from app.modules.utils.analytics import analyze_user_behavior
from app.modules.search import SearchParams, SearchResponse
from app.modules.search.service import (
    update_search_statistics,
)
from app.modules.search.typesense_client import get_typesense_client
from ..analytics import (
    record_search_query,
    get_popular_searches,
    get_recent_searches,
    get_user_searches,
    generate_search_trends_chart,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])


def _cache_client():
    """Endpoint: _cache_client."""
    app_env = os.getenv("APP_ENV", settings.environment).lower()
    if app_env == "test":
        return None
    client = getattr(settings, "redis_client", None)
    return client


@router.post("/", response_model=SearchResponse)
async def search(
    search_params: SearchParams,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Main search endpoint.

    - Receives search parameters from the user.
    - Records the search query.
    - Gets spell-check suggestions.
    - Searches posts and sorts results.
    - Retrieves popular and user search suggestions.
    - Caches results for one hour using Redis.

    Returns a SearchResponse with results, spell suggestion, and search suggestions.
    """
    cache_key = f"search:{search_params.query}:{search_params.sort_by}"
    cache_client = _cache_client()
    if cache_client:
        try:
            cached_payload = cache_client.get(cache_key)
        except Exception as exc:  # pragma: no cover - defensive cache fallback
            logger.warning("Redis unavailable, skipping cache: %s", exc)
            cache_client = None
        else:
            if cached_payload:
                return json.loads(cached_payload)

    # Record the search query
    record_search_query(db, search_params.query, current_user.id)

    suggestions = get_spell_suggestions(search_params.query)
    spell_suggestion = format_spell_suggestions(search_params.query, suggestions)

    query = search_posts(search_params.query, db)
    sorted_query = sort_search_results(
        query, search_params.sort_by, search_text=search_params.query
    )
    results = sorted_query.all()
    typesense_client = get_typesense_client()
    if typesense_client:
        try:
            ts_hits = typesense_client.search_posts(
                search_params.query, limit=max(len(results), 10)
            )
            post_ids: list[int] = []
            for hit in ts_hits:
                document = (hit or {}).get("document") or {}
                post_id = document.get("post_id") or document.get("id")
                if post_id is None:
                    continue
                try:
                    post_ids.append(int(post_id))
                except (TypeError, ValueError):
                    continue
            if post_ids:
                posts_by_id = {
                    post.id: post
                    for post in db.query(models.Post)
                    .filter(models.Post.id.in_(post_ids))
                    .all()
                }
                ordered = [posts_by_id[pid] for pid in post_ids if pid in posts_by_id]
                if ordered:
                    results = ordered
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Typesense search failed, using default search: %s", exc)

    # Get search suggestions from popular and user history
    popular_searches = get_popular_searches(db, limit=3)
    user_searches = get_user_searches(db, current_user.id, limit=2)
    search_suggestions = list(
        set([stat.query for stat in popular_searches + user_searches])
    )

    search_response = {
        "results": results,
        "spell_suggestion": spell_suggestion,
        "search_suggestions": search_suggestions,
    }

    if results and cache_client:
        try:
            cache_client.setex(
                cache_key,
                3600,
                json.dumps(jsonable_encoder(search_response)),
            )
        except RedisError:  # pragma: no cover - cache errors are ignored
            pass

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
    """
    Advanced search endpoint for posts.

    - Allows filtering by query text, date range, category, and author.
    - Supports search scope: title, content, comments, or all.

    Returns total count and a list of posts formatted as PostOut.
    """
    search_query = db.query(models.Post)

    if query:
        if search_scope in ["title", "all"]:
            search_query = search_query.filter(models.Post.title.ilike(f"%{query}%"))
        if search_scope in ["content", "all"]:
            search_query = search_query.filter(models.Post.content.ilike(f"%{query}%"))
        if search_scope == "comments":
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

    return {"total": total, "posts": [schemas.PostOut.model_validate(post) for post in posts]}


@router.get("/categories", response_model=List[schemas.Category])
async def get_categories(db: Session = Depends(get_db)):
    """Endpoint: get_categories."""
    categories = db.query(models.Category).all()
    return categories


@router.get("/authors", response_model=List[schemas.UserOut])
async def get_authors(db: Session = Depends(get_db)):
    """Endpoint: get_authors."""
    authors = db.query(models.User).filter(models.User.post_count > 0).all()
    return authors


@router.get("/autocomplete", response_model=List[schemas.SearchSuggestionOut])
async def autocomplete(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    """
    Return autocomplete suggestions for a given query.

    - Searches for suggestions starting with the query.
    - Orders by frequency and caches results for 5 minutes.
    """
    cache_key = f"autocomplete:{query}"
    cache_client = _cache_client()
    if cache_client:
        try:
            cached_payload = cache_client.get(cache_key)
        except Exception:
            cache_client = None
        else:
            if cached_payload:
                return json.loads(cached_payload)

    suggestions = (
        db.query(models.SearchSuggestion)
        .filter(models.SearchSuggestion.term.ilike(f"{query}%"))
        .order_by(models.SearchSuggestion.frequency.desc())
        .limit(limit)
        .all()
    )

    result = [schemas.SearchSuggestionOut.model_validate(s) for s in suggestions]
    if cache_client:
        try:
            payload = jsonable_encoder(result)
            cache_client.setex(cache_key, 300, json.dumps(payload))
        except Exception:
            pass

    return result


@router.post("/record-search")
async def record_search(
    term: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Record a user's search term.

    - Increments frequency if the term exists or adds a new record.
    """
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
    """
    Get the most popular search queries.
    """
    return get_popular_searches(db, limit)


@router.get("/recent", response_model=List[schemas.SearchStatOut])
async def recent_searches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Get the most recent search queries.
    """
    return get_recent_searches(db, limit)


@router.get("/trends")
async def search_trends(current_user: models.User = Depends(oauth2.get_current_admin)):
    """Endpoint: search_trends."""
    chart = generate_search_trends_chart()
    return {"chart": chart}


@router.get("/smart", response_model=List[schemas.PostOut])
async def smart_search(
    query: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    """
    Smart search using user search history and behavior.

    - Retrieves the user's recent search history.
    - Performs an initial search using plainto_tsquery.
    - Scores results based on user behavior.
    - Updates search statistics.

    Returns a list of posts sorted by relevance.
    """
    # Get user search history (last 20 queries)
    user_history = (
        db.query(models.SearchStatistics.query)
        .filter(models.SearchStatistics.user_id == current_user.id)
        .order_by(models.SearchStatistics.last_searched.desc())
        .limit(20)
        .all()
    )
    user_history = [item[0] for item in user_history]

    # Perform initial search using plainto_tsquery
    search_query = func.plainto_tsquery("english", query)
    initial_results = (
        db.query(models.Post)
        .filter(models.Post.search_vector.op("@@")(search_query))
        .all()
    )

    # Score results based on user behavior
    scored_results = [
        (post, analyze_user_behavior(user_history, post.content))
        for post in initial_results
    ]
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # Update search statistics for the user
    update_search_statistics(db, current_user.id, query)

    return [
        schemas.PostOut.model_validate(post)
        for post, _ in scored_results[skip : skip + limit]
    ]
