"""Test module for test query helpers."""
import base64

from app import models
from app.core.database.query_helpers import (
    cursor_paginate,
    optimize_count_query,
    paginate_query,
)


def _create_users(session, count=3):
    """Helper for  create users."""
    users = [
        models.User(
            email=f"qh_user{idx}@example.com",
            hashed_password="hashed",
            is_verified=True,
        )
        for idx in range(count)
    ]
    session.add_all(users)
    session.commit()
    return users


def test_paginate_query_clamps_limits(session):
    """Test case for test paginate query clamps limits."""
    _create_users(session, count=5)
    q = session.query(models.User).filter(models.User.email.like("qh_user%@example.com"))

    limited = paginate_query(q, skip=-10, limit=0)
    rows = limited.all()
    assert len(rows) == 1  # limit clamped to at least 1

    capped = paginate_query(q, skip=0, limit=1000)
    assert len(capped.all()) == 5  # total rows, but limit capped internally


def test_cursor_paginate_roundtrip(session):
    """Test case for test cursor paginate roundtrip."""
    users = _create_users(session, count=3)
    q = session.query(models.User).filter(models.User.email.like("qh_user%@example.com"))

    first_page = cursor_paginate(q, limit=2, order_desc=False)
    assert first_page["has_next"] is True
    assert first_page["count"] == 2
    assert base64.b64decode(first_page["next_cursor"])  # valid cursor

    next_page = cursor_paginate(
        q, cursor=first_page["next_cursor"], limit=2, order_desc=False
    )
    assert next_page["has_next"] is False
    assert {u.id for u in next_page["items"]} == {users[-1].id}


def test_optimize_count_query_matches_count(session):
    """Test case for test optimize count query matches count."""
    _create_users(session, count=4)
    q = session.query(models.User)
    assert optimize_count_query(q) == q.count()
