"""Analytics utilities for notifications."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models


class NotificationAnalyticsService:
    """Provides notification analytics and statistics."""

    def __init__(self, db: Session):
        self.db = db

    def get_delivery_stats(self, user_id: Optional[int] = None):
        """Return delivery statistics aggregated for optional user context."""
        query = self.db.query(models.NotificationDeliveryLog)
        if user_id:
            query = query.join(models.Notification).filter(
                models.Notification.user_id == user_id
            )
        total = query.count()
        successful = query.filter(
            models.NotificationDeliveryLog.status == "delivered"
        ).count()
        failed = query.filter(models.NotificationDeliveryLog.status == "failed").count()
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
        }

    def get_user_engagement(self, user_id: int, days: int = 30):
        """Compute read vs total ratio over the requested window."""
        cutoff_date = datetime.now() - timedelta(days=days)
        notifications = (
            self.db.query(models.Notification)
            .filter(
                models.Notification.user_id == user_id,
                models.Notification.created_at >= cutoff_date,
            )
            .all()
        )
        total_notifications = len(notifications)
        read_notifications = sum(1 for notif in notifications if notif.is_read)
        return {
            "total_notifications": total_notifications,
            "read_notifications": read_notifications,
            "engagement_rate": (
                (read_notifications / total_notifications * 100)
                if total_notifications > 0
                else 0
            ),
        }

    async def get_user_statistics(self, user_id: int, days: int = 30):
        """Async-friendly wrapper returning engagement metrics."""
        return self.get_user_engagement(user_id, days)

    async def get_detailed_analytics(self, days: int = 30):
        """Return combined delivery and engagement analytics."""
        delivery = self.get_delivery_stats()
        engagement_snapshot = {
            "engagement_rate": 0,
            "total_notifications": 0,
            "read_notifications": 0,
        }
        # attempt to derive aggregate engagement across users (best-effort)
        total_notifications = (
            self.db.query(models.Notification)
            .filter(
                models.Notification.created_at >= datetime.now() - timedelta(days=days)
            )
            .count()
        )
        if total_notifications:
            read_notifications = (
                self.db.query(models.Notification)
                .filter(
                    models.Notification.created_at
                    >= datetime.now() - timedelta(days=days),
                    models.Notification.is_read.is_(True),
                )
                .count()
            )
            engagement_snapshot = {
                "total_notifications": total_notifications,
                "read_notifications": read_notifications,
                "engagement_rate": (
                    (read_notifications / total_notifications * 100)
                    if total_notifications
                    else 0
                ),
            }
        return {"delivery": delivery, "engagement": engagement_snapshot}


__all__ = ["NotificationAnalyticsService"]
