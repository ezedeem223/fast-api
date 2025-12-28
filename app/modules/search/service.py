"""Search domain services reused across routers and background jobs.

Notes:
- Integrates with Typesense when enabled; otherwise falls back to DB search.
- Search statistics updated per user query and can be cached via app.modules.search.cache helpers.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.modules.search.schemas import SearchSuggestionOut


def update_search_statistics(db: Session, user_id: int, query: str) -> None:
    """
    Update the search statistics for a user.

    - If a record exists, increment the count and update the last searched time.
    - Otherwise, create a new record.
    """
    stat = (
        db.query(models.SearchStatistics)
        .filter(
            models.SearchStatistics.user_id == user_id,
            models.SearchStatistics.term == query,
        )
        .first()
    )

    if stat:
        stat.searches += 1
        stat.updated_at = func.now()
    else:
        new_stat = models.SearchStatistics(user_id=user_id, term=query, searches=1)
        db.add(new_stat)

    db.commit()


def update_search_suggestions(db: Session) -> List[SearchSuggestionOut]:
    """
    Update search suggestions based on popular search queries.

    Returns:
        List[SearchSuggestionOut]: List of search suggestions.
    """
    suggestions = (
        db.query(models.SearchSuggestion)
        .order_by(models.SearchSuggestion.usage_count.desc())
        .limit(10)
        .all()
    )
    return [SearchSuggestionOut.model_validate(s) for s in suggestions]


__all__ = ["update_search_statistics", "update_search_suggestions"]
