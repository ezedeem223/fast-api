"""Database-aware helpers for SQL column defaults."""

from sqlalchemy.sql import text


def timestamp_default():
    """Return a server-side timestamp default portable across dialects."""
    return text("CURRENT_TIMESTAMP")


__all__ = ["timestamp_default"]
