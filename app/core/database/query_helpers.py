"""
Query optimization helpers for eager loading and pagination.
"""

from typing import Any, List, Type, Dict, Optional
from sqlalchemy.orm import Query, joinedload, selectinload, contains_eager
from sqlalchemy import desc, asc, func
import base64
import json


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


def cursor_paginate(
    query: Query,
    cursor: Optional[str] = None,
    limit: int = 20,
    cursor_column: str = "id",
    order_desc: bool = True,
) -> Dict[str, Any]:
    """
    Pagination محسّن باستخدام cursor بدلاً من offset
    أسرع بكثير للجداول الكبيرة

    Args:
        query: SQLAlchemy query
        cursor: Base64 encoded cursor من الصفحة السابقة
        limit: عدد النتائج
        cursor_column: اسم العمود المستخدم للـ cursor
        order_desc: ترتيب تنازلي أو تصاعدي

    Returns:
        Dict يحتوي على items, next_cursor, has_next
    """
    # فك تشفير الـ cursor
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode("utf-8")
            cursor_value = json.loads(decoded)
        except Exception:
            cursor_value = None
    else:
        cursor_value = None

    # الحصول على model class من query
    model = query.column_descriptions[0]["entity"]

    # إضافة شرط الـ cursor
    if cursor_value is not None:
        column = getattr(model, cursor_column)
        if order_desc:
            query = query.filter(column < cursor_value)
        else:
            query = query.filter(column > cursor_value)

    # ترتيب النتائج
    column = getattr(model, cursor_column)
    if order_desc:
        query = query.order_by(desc(column))
    else:
        query = query.order_by(asc(column))

    # جلب limit + 1 للتحقق من وجود صفحة تالية
    items = query.limit(limit + 1).all()

    # التحقق من وجود صفحة تالية
    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    # إنشاء next_cursor
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
    تحميل العلاقات بشكل مجمّع لتجنب N+1 problem

    Args:
        query: SQLAlchemy query
        *relationships: أسماء العلاقات للتحميل

    Returns:
        Query with loaded relationships
    """
    for rel in relationships:
        if isinstance(rel, tuple):
            # تحميل متداخل
            query = query.options(selectinload(rel[0]).selectinload(rel[1]))
        else:
            # تحميل بسيط
            query = query.options(selectinload(rel))

    return query


def optimize_count_query(query: Query) -> int:
    """
    تحسين استعلام count()

    Args:
        query: SQLAlchemy query

    Returns:
        عدد النتائج
    """
    # استخدام subquery للـ count بدلاً من count(*) المباشر
    count_query = query.statement.with_only_columns([func.count()]).order_by(None)
    return query.session.execute(count_query).scalar()


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
