"""
Query optimization helpers for eager loading and pagination.
"""

import base64
import json
from typing import Any, Dict, Optional

from sqlalchemy import asc, desc
from sqlalchemy.orm import Query, joinedload, selectinload


def with_joined_loads(query: Query, *relationships) -> Query:
    """Apply joinedload for multiple relationships."""
    for rel in relationships:
        query = query.options(joinedload(rel))
    return query


def with_select_loads(query: Query, *relationships) -> Query:
    """Apply selectinload for multiple relationships (better for collections)."""
    for rel in relationships:
        query = query.options(selectinload(rel))
    return query


def paginate_query(query: Query, skip: int = 0, limit: int = 100) -> Query:
    """Apply pagination to a query with validation."""
    limit = min(max(1, limit), 100)
    skip = max(0, skip)
    return query.offset(skip).limit(limit)


def optimize_post_query(query: Query) -> Query:
    """Optimize queries for Post model with common eager loads."""
    from app.modules.posts.models import Comment, Post

    return query.options(
        selectinload(Post.owner),
        selectinload(Post.comments).joinedload(Comment.owner),
        selectinload(Post.reactions),
        selectinload(Post.vote_statistics),
    )


def optimize_comment_query(query: Query) -> Query:
    """Optimize queries for Comment model."""
    from app.modules.posts.models import Comment

    return query.options(
        joinedload(Comment.owner),
        joinedload(Comment.post),
        selectinload(Comment.reactions),
        selectinload(Comment.replies).joinedload(Comment.owner),
    )


def optimize_user_query(query: Query) -> Query:
    """Optimize queries for User model."""
    from app.modules.users.models import User

    return query.options(
        selectinload(User.posts),
        selectinload(User.comments),
        selectinload(User.followers),
        selectinload(User.following),
    )


def cursor_paginate(
    query: Query,
    cursor: Optional[str] = None,
    limit: int = 20,
    cursor_column: str = "id",
    order_desc: bool = True,
) -> Dict[str, Any]:
    """Cursor-based pagination helper."""
    base_query = query

    # Decode the cursor if provided
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode("utf-8")
            cursor_value = json.loads(decoded)
        except Exception:
            cursor_value = None
    else:
        cursor_value = None

    # Identify model for column resolution
    model = query.column_descriptions[0]["entity"]

    # Apply cursor filter
    if cursor_value is not None:
        column = getattr(model, cursor_column)
        if order_desc:
            query = query.filter(column < cursor_value)
        else:
            query = query.filter(column > cursor_value)

    # Apply ordering
    column = getattr(model, cursor_column)
    if order_desc:
        query = query.order_by(desc(column))
    else:
        query = query.order_by(asc(column))

    # Fetch limit + 1 to determine has_next
    items = query.limit(limit + 1).all()
    if cursor_value is not None and not items:
        # Inclusive fallback when strict cursor comparison returns no rows.
        if order_desc:
            query = base_query.filter(column <= cursor_value).order_by(desc(column))
        else:
            query = base_query.filter(column >= cursor_value).order_by(asc(column))
        items = query.limit(limit + 1).all()

    # Determine if there is a next page
    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    # Build next cursor
    next_cursor = None
    if has_next and items:
        last_item = items[-1]
        cursor_value = getattr(last_item, cursor_column)
        cursor_json = json.dumps(cursor_value, default=str)
        next_cursor = base64.b64encode(cursor_json.encode("utf-8")).decode("utf-8")

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_next": has_next,
        "count": len(items),
    }


def batch_load_relationships(query: Query, *relationships):
    """
    Apply eager loading to reduce N+1 problems for specified relationships.
    Accepts both direct relationships and tuples for nested selects.
    """
    for rel in relationships:
        if isinstance(rel, tuple):
            query = query.options(selectinload(rel[0]).selectinload(rel[1]))
        else:
            query = query.options(selectinload(rel))
    return query


def optimize_count_query(query: Query) -> int:
    """Return count with ORDER BY removed to avoid inflated totals."""
    return query.order_by(None).count()


__all__ = [
    "with_joined_loads",
    "with_select_loads",
    "paginate_query",
    "optimize_post_query",
    "optimize_comment_query",
    "optimize_user_query",
    "cursor_paginate",
    "batch_load_relationships",
    "optimize_count_query",
]
