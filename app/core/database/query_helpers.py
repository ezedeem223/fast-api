"""
Query optimization helpers for eager loading and pagination.
"""

from typing import Any, List, Type
from sqlalchemy.orm import Query, joinedload, selectinload, contains_eager


def with_joined_loads(query: Query, *relationships) -> Query:
    """
    Apply joinedload for multiple relationships.

    Example:
        query = with_joined_loads(query, Post.author, Post.comments)
    """
    for rel in relationships:
        query = query.options(joinedload(rel))
    return query


def with_select_loads(query: Query, *relationships) -> Query:
    """
    Apply selectinload for multiple relationships (better for collections).

    Example:
        query = with_select_loads(query, Post.comments, Post.reactions)
    """
    for rel in relationships:
        query = query.options(selectinload(rel))
    return query


def paginate_query(query: Query, skip: int = 0, limit: int = 100) -> Query:
    """
    Apply pagination to a query with validation.

    Args:
        query: SQLAlchemy query object
        skip: Number of records to skip
        limit: Maximum records to return (capped at 100)

    Returns:
        Paginated query
    """
    # Validate and cap limit
    limit = min(max(1, limit), 100)
    skip = max(0, skip)

    return query.offset(skip).limit(limit)


def optimize_post_query(query: Query) -> Query:
    """
    Optimize queries for Post model with common eager loads.

    Prevents N+1 queries when fetching posts with related data.
    """
    return query.options(
        joinedload("owner"),  # Always load post owner
        selectinload("comments").joinedload("owner"),  # Load comments with their owners
        selectinload("reactions"),  # Load reactions
        selectinload("vote_statistics"),  # Load vote stats
    )


def optimize_comment_query(query: Query) -> Query:
    """
    Optimize queries for Comment model.
    """
    return query.options(
        joinedload("owner"),  # Load comment owner
        joinedload("post"),  # Load parent post
        selectinload("reactions"),  # Load reactions
        selectinload("replies").joinedload("owner"),  # Load replies with owners
    )


def optimize_user_query(query: Query) -> Query:
    """
    Optimize queries for User model.
    """
    return query.options(
        selectinload("posts"),
        selectinload("comments"),
        selectinload("followers"),
        selectinload("following"),
    )


__all__ = [
    "with_joined_loads",
    "with_select_loads",
    "paginate_query",
    "optimize_post_query",
    "optimize_comment_query",
    "optimize_user_query",
]
