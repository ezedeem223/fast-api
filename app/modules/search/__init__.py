"""Search domain package."""

from .schemas import (
    AdvancedSearchQuery,
    AdvancedSearchResponse,
    SearchParams,
    SearchResponse,
    SearchStatOut,
    SearchStatistics,
    SearchStatisticsBase,
    SearchStatisticsCreate,
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
