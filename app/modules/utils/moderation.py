"""Moderation-specific utility helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .common import logger
from app.modules.moderation.models import AuditLog


def log_event(db: Session, event_type: str, metadata: Optional[dict] = None) -> None:
    """Log moderation events (placeholder for future persistence)."""
    logger.info("Block event %s - metadata=%s", event_type, metadata)


def log_admin_action(
    db: Session, admin_id: int, action: str, metadata: Optional[dict] = None
) -> None:
    """Log admin actions for auditing purposes."""
    logger.info("Admin %s action %s - metadata=%s", admin_id, action, metadata)
    try:
        audit = AuditLog(
            admin_id=admin_id,
            action=action,
            details=metadata or {},
        )
        db.add(audit)
        db.commit()
    except Exception:
        db.rollback()
        # Keep logging but avoid breaking callers
        logger.warning("Failed to persist audit log for admin=%s action=%s", admin_id, action)


__all__ = ["log_event", "log_admin_action"]
