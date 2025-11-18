"""Search utilities including spell checking."""

from __future__ import annotations

from typing import List

import logging

from cachetools import TTLCache
from sqlalchemy import asc, desc, func, or_, text
from sqlalchemy.orm import Query, Session
from spellchecker import SpellChecker
from sqlalchemy import create_engine

from app import models
from app.core.config import settings

logger = logging.getLogger(__name__)
spell = SpellChecker()
search_cache = TTLCache(maxsize=100, ttl=60)


def _resolve_bind(session: Session | None):
    if session is None:
        return None
    if hasattr(session, "get_bind"):
        try:
            bind = session.get_bind()
            if bind is not None:
                return bind
        except Exception:
            pass
    return getattr(session, "bind", None)


def _is_sqlite(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", "")
    return bool(name) and str(name).lower().startswith("sqlite")


def _uses_sqlite(session: Session | None) -> bool:
    bind = _resolve_bind(session)
    if bind is not None:
        return _is_sqlite(bind)
    db_url = (settings.test_database_url or settings.database_url or "").lower()
    return db_url.startswith("sqlite")


def update_search_vector():
    """Update full-text search vector for posts."""
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE posts
                SET search_vector = to_tsvector('english',
                    coalesce(title,'') || ' ' ||
                    coalesce(content,'') || ' ' ||
                    coalesce(media_text,''))
                """
            )
        )


def search_posts(query: str, db: Session) -> Query:
    """Return a base query for posts matching the search parameters."""
    like_query = f"%{query}%"
    base_query = db.query(models.Post)

    if _uses_sqlite(db):
        logger.debug("search_posts using SQLite fallback")
        return base_query.filter(
            or_(
                models.Post.title.ilike(like_query),
                models.Post.content.ilike(like_query),
                models.Post.media_text.ilike(like_query),
            )
        )

    search_query = func.plainto_tsquery("english", query)
    return base_query.filter(
        or_(
            models.Post.search_vector.op("@@")(search_query),
            models.Post.media_text.ilike(like_query),
        )
    )


def get_spell_suggestions(query: str) -> List[str]:
    """Generate spelling suggestions for the query."""
    words = query.split()
    suggestions = []
    for word in words:
        if word not in spell:
            suggestions.append(spell.correction(word))
        else:
            suggestions.append(word)
    return suggestions


def format_spell_suggestions(original_query: str, suggestions: List[str]) -> str:
    """Return formatted spelling suggestion message."""
    if original_query.lower() != " ".join(suggestions).lower():
        return f"Did you mean: {' '.join(suggestions)}?"
    return ""


def sort_search_results(query: Query, sort_option: str, *, search_text: str):
    """Sort a SQLAlchemy query by relevance, date, or popularity."""
    if sort_option == "RELEVANCE":
        if _uses_sqlite(getattr(query, "session", None)):
            return query.order_by(desc(models.Post.created_at))
        ts_query = func.plainto_tsquery("english", search_text)
        return query.order_by(
            desc(
                func.ts_rank(
                    models.Post.search_vector,
                    ts_query,
                )
            )
        )
    if sort_option == "DATE_DESC":
        return query.order_by(desc(models.Post.created_at))
    if sort_option == "DATE_ASC":
        return query.order_by(asc(models.Post.created_at))
    if sort_option == "POPULARITY":
        return query.order_by(desc(models.Post.votes))
    return query


__all__ = [
    "spell",
    "search_cache",
    "update_search_vector",
    "search_posts",
    "get_spell_suggestions",
    "format_spell_suggestions",
    "sort_search_results",
]
