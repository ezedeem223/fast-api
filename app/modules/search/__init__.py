"""Search domain package with schemas and stats update helpers."""

from .schemas import (
    AdvancedSearchQuery,
    AdvancedSearchResponse,
    SearchParams,
    SearchResponse,
    SearchStatistics,
    SearchStatisticsBase,
    SearchStatisticsCreate,
    SearchStatOut,
    SearchSuggestionOut,
)
from .service import update_search_statistics, update_search_suggestions

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
    "update_search_statistics",
    "update_search_suggestions",
]
