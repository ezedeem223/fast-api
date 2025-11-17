"""Event logging helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .common import logger


def log_user_event(
    db: Session, user_id: int, event: str, metadata: Optional[dict] = None
):
    """Log user events (currently emitted via stdout/logger)."""
    log_message = f"User Event - User: {user_id}, Event: {event}, Metadata: {metadata}"
    logger.info(log_message)


__all__ = ["log_user_event"]
