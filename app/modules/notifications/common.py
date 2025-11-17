"""Shared helpers and state for the notifications domain."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from cachetools import TTLCache
from sqlalchemy.orm import Session

logger = logging.getLogger("app.notifications")

# Shared caches leveraged across notification services
notification_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)
delivery_status_cache: TTLCache = TTLCache(maxsize=5000, ttl=3600)
priority_notification_cache: TTLCache = TTLCache(maxsize=500, ttl=60)

F = TypeVar("F", bound=Callable[..., Any])


def get_model_by_id(db: Session, model, object_id: Any) -> Optional[Any]:
    """Fetch a SQLAlchemy model instance by primary key."""
    try:
        return db.query(model).filter(model.id == object_id).first()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error fetching %s(%s): %s", model.__name__, object_id, exc)
        return None


def get_or_create(db: Session, model, defaults: Optional[dict] = None, **kwargs) -> Any:
    """Fetch or create an instance matching the provided filters."""
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance

    params = dict(kwargs)
    if defaults:
        params.update(defaults)

    instance = model(**params)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def handle_async_errors(func: F) -> F:
    """Log errors from async helpers instead of swallowing them."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error in %s: %s", func.__name__, exc)
            raise

    return wrapper  # type: ignore[return-value]


__all__ = [
    "logger",
    "notification_cache",
    "delivery_status_cache",
    "priority_notification_cache",
    "get_model_by_id",
    "get_or_create",
    "handle_async_errors",
]
