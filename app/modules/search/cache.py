"""Utility helpers for caching search statistics/suggestions in Redis.

Design:
- Fail-open: if Redis is absent/unreachable, functions return None and bypass cache hits.
- Keys are plain strings; payloads are JSON-serialized with TTL.
- Used by analytics/search services to avoid DB hits for popular/recent/user stats.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from app.core.config import settings


def _client():
    """Helper for  client."""
    return settings.redis_client


def _ensure_str(value: Any) -> Optional[str]:
    """Helper for  ensure str."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    return str(value)


def get_cached_json(key: str) -> Optional[Any]:
    """Return cached json."""
    client = _client()
    if not client:
        # Fail open: absent Redis means no cache hit rather than raising in hot paths.
        return None
    payload = _ensure_str(client.get(key))
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        client.delete(key)
        return None


def set_cached_json(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Helper for set cached json."""
    client = _client()
    if not client:
        return
    client.setex(key, ttl_seconds, json.dumps(value, default=_json_serializer))


def delete_keys(keys: Iterable[str]) -> None:
    """Delete keys."""
    client = _client()
    if not client:
        return
    keys = list(keys)
    if keys:
        client.delete(*keys)


def delete_pattern(pattern: str) -> None:
    """Delete pattern."""
    client = _client()
    if not client:
        return
    to_delete = list(client.scan_iter(match=pattern))
    if to_delete:
        client.delete(*to_delete)


def _json_serializer(value: Any):
    """Helper for  json serializer."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def popular_cache_key(limit: int) -> str:
    """Helper for popular cache key."""
    return f"search:stats:popular:{limit}"


def recent_cache_key(limit: int) -> str:
    """Helper for recent cache key."""
    return f"search:stats:recent:{limit}"


def user_cache_key(user_id: int, limit: int) -> str:
    """Helper for user cache key."""
    return f"search:stats:user:{user_id}:{limit}"


def invalidate_stats_cache(for_user_id: Optional[int] = None) -> None:
    """Helper for invalidate stats cache."""
    if for_user_id is not None:
        delete_pattern(f"search:stats:user:{for_user_id}:*")
    delete_pattern("search:stats:popular:*")
    delete_pattern("search:stats:recent:*")
