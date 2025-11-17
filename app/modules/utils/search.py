"""Search utilities including spell checking."""

from __future__ import annotations

from typing import List

from cachetools import TTLCache
from sqlalchemy import asc, desc, func, or_, text
from sqlalchemy.orm import Query, Session
from spellchecker import SpellChecker
from sqlalchemy import create_engine

from app import models
from app.core.config import settings

spell = SpellChecker()
search_cache = TTLCache(maxsize=100, ttl=60)


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
    search_query = func.plainto_tsquery("english", query)
    return db.query(models.Post).filter(
        or_(
            models.Post.search_vector.op("@@")(search_query),
            models.Post.media_text.ilike(f"%{query}%"),
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
