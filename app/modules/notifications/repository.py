"""Data-access helpers for notifications domain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session, Query

from app.modules.notifications import models as notification_models


class NotificationRepository:
    """Encapsulate notification-specific database operations."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ prefs
    def get_preferences(self, user_id: int) -> Optional[notification_models.NotificationPreferences]:
        return (
            self.db.query(notification_models.NotificationPreferences)
            .filter(notification_models.NotificationPreferences.user_id == user_id)
            .first()
        )

    def ensure_preferences(self, user_id: int) -> notification_models.NotificationPreferences:
        prefs = self.get_preferences(user_id)
        if prefs:
            return prefs
        prefs = notification_models.NotificationPreferences(user_id=user_id)
        self.db.add(prefs)
        self.db.commit()
        self.db.refresh(prefs)
        return prefs

    # ----------------------------------------------------------------- queries
    def build_notifications_query(
        self,
        *,
        user_id: int,
        include_read: bool,
        include_archived: bool,
        category: Optional[notification_models.NotificationCategory],
        priority: Optional[notification_models.NotificationPriority],
        status: Optional[notification_models.NotificationStatus] = None,
        since: Optional[datetime] = None,
    ) -> Query:
        query = (
            self.db.query(notification_models.Notification)
            .filter(notification_models.Notification.user_id == user_id)
            .filter(notification_models.Notification.is_deleted.is_(False))
        )
        if not include_read:
            query = query.filter(notification_models.Notification.is_read.is_(False))
        if not include_archived:
            query = query.filter(notification_models.Notification.is_archived.is_(False))
        if category:
            query = query.filter(notification_models.Notification.category == category)
        if priority:
            query = query.filter(notification_models.Notification.priority == priority)
        if status:
            query = query.filter(notification_models.Notification.status == status)
        if since:
            query = query.filter(notification_models.Notification.created_at >= since)
        return query.order_by(notification_models.Notification.created_at.desc())

    def get_notification_for_user(self, notification_id: int, user_id: int):
        return (
            self.db.query(notification_models.Notification)
            .filter(
                notification_models.Notification.id == notification_id,
                notification_models.Notification.user_id == user_id,
                notification_models.Notification.is_deleted.is_(False),
            )
            .first()
        )

    # --------------------------------------------------------------- mutations
    def mark_notification_as_read(self, notification_id: int, user_id: int):
        notification = self.get_notification_for_user(notification_id, user_id)
        if notification and not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def mark_all_as_read(self, user_id: int) -> int:
        updated = (
            self.db.query(notification_models.Notification)
            .filter(
                notification_models.Notification.user_id == user_id,
                notification_models.Notification.is_read.is_(False),
                notification_models.Notification.is_deleted.is_(False),
            )
            .update(
                {"is_read": True, "read_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        self.db.commit()
        return updated or 0

    def archive_notification(self, notification_id: int, user_id: int):
        notification = self.get_notification_for_user(notification_id, user_id)
        if notification:
            notification.is_archived = True
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def soft_delete_notification(self, notification_id: int, user_id: int):
        notification = self.get_notification_for_user(notification_id, user_id)
        if notification:
            notification.is_deleted = True
            notification.is_archived = True
            self.db.commit()
        return notification

    def create_notification(self, **kwargs) -> notification_models.Notification:
        notification = notification_models.Notification(**kwargs)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    # -------------------------------------------------------------- analytics
    def unread_count(self, user_id: int) -> int:
        return (
            self.db.query(notification_models.Notification)
            .filter(
                notification_models.Notification.user_id == user_id,
                notification_models.Notification.is_read.is_(False),
                notification_models.Notification.is_deleted.is_(False),
            )
            .count()
        )

    def unseen_count(self, user_id: int) -> int:
        return (
            self.db.query(notification_models.Notification)
            .filter(
                notification_models.Notification.user_id == user_id,
                notification_models.Notification.seen_at.is_(None),
                notification_models.Notification.is_deleted.is_(False),
            )
            .count()
        )

    def get_unread_summary(self, user_id: int) -> Dict[str, Any]:
        unread_count, last_unread_at, urgent_count = (
            self.db.query(
                func.count(notification_models.Notification.id),
                func.max(notification_models.Notification.created_at),
                func.sum(
                    case(
                        (
                            notification_models.Notification.priority.in_(
                                [
                                    notification_models.NotificationPriority.HIGH,
                                    notification_models.NotificationPriority.URGENT,
                                ]
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .filter(
                notification_models.Notification.user_id == user_id,
                notification_models.Notification.is_read.is_(False),
                notification_models.Notification.is_deleted.is_(False),
            )
            .one()
        )
        unseen = self.unseen_count(user_id)
        return {
            "unread_count": unread_count or 0,
            "unseen_count": unseen,
            "unread_urgent_count": urgent_count or 0,
            "last_unread_at": last_unread_at,
        }

    def cleanup_archived(self, cutoff) -> int:
        deleted = (
            self.db.query(notification_models.Notification)
            .filter(
                notification_models.Notification.created_at < cutoff,
                notification_models.Notification.is_archived.is_(True),
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted or 0

    def delivery_log_counts(self, status: str) -> int:
        return (
            self.db.query(notification_models.NotificationDeliveryLog)
            .filter(notification_models.NotificationDeliveryLog.status == status)
            .count()
        )

    def delivery_log_total(self) -> int:
        return self.db.query(notification_models.NotificationDeliveryLog).count()


__all__ = ["NotificationRepository"]
