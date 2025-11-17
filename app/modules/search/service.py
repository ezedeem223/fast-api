"""Search domain services reused across routers and background jobs."""

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


def update_search_suggestions(db: Session) -> List[SearchSuggestionOut]:
    """
    Update search suggestions based on popular search queries.

    Returns:
        List[SearchSuggestionOut]: List of search suggestions.
    """
    suggestions = (
        db.query(models.SearchSuggestion)
        .order_by(models.SearchSuggestion.frequency.desc())
        .limit(10)
        .all()
    )
    return [SearchSuggestionOut.model_validate(s) for s in suggestions]


__all__ = ["update_search_statistics", "update_search_suggestions"]
