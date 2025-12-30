"""Pydantic schemas for search and search statistics."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.posts.schemas import PostOut
from app.modules.users.schemas import SortOption


class SearchParams(BaseModel):
    """Parameters accepted by the primary search endpoint."""

    query: str
    sort_by: SortOption = SortOption.RELEVANCE


class AdvancedSearchQuery(BaseModel):
    """Payload used by the advanced search endpoint."""

    keyword: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    categories: Optional[List[int]] = None
    author_id: Optional[int] = None
    search_in: List[str] = Field(default=["title", "content", "comments"])


class SearchStatOut(BaseModel):
    """Top-level search statistics row."""

    query: str
    count: int
    last_searched: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchStatisticsBase(BaseModel):
    """Shared base for persisted search statistics."""

    query: str
    count: int
    last_searched: datetime


class SearchStatisticsCreate(SearchStatisticsBase):
    """Creation schema for a statistics row."""

    pass


class SearchStatistics(SearchStatisticsBase):
    """Database-backed statistics row."""

    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """API response for the main search endpoint."""

    results: List[PostOut]
    spell_suggestion: str
    search_suggestions: List[str]


class AdvancedSearchResponse(BaseModel):
    """Response payload for the advanced search endpoint."""

    total: int
    posts: List[PostOut]


class SearchSuggestionOut(BaseModel):
    """Individual cached search suggestion."""

    term: str

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "AdvancedSearchQuery",
    "AdvancedSearchResponse",
    "SearchParams",
    "SearchResponse",
    "SearchStatOut",
    "SearchStatistics",
    "SearchStatisticsBase",
    "SearchStatisticsCreate",
    "SearchSuggestionOut",
]
