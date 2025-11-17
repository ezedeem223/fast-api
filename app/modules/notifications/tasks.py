"""Reusable task helpers for the notifications domain."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from firebase_admin import messaging
from sqlalchemy.orm import Session

from app import models as legacy_models
from app.modules.notifications import models as notification_models
from .common import logger


def cleanup_old_notifications_task(
    db: Session, *, archive_days: int = 30, delete_days: int = 90
) -> None:
    """Archive read notifications and delete long-lived archived entries."""
    thirty_days_ago = datetime.utcnow() - timedelta(days=archive_days)
    db.query(notification_models.Notification).filter(
        notification_models.Notification.is_read.is_(True),
        notification_models.Notification.created_at < thirty_days_ago,
        notification_models.Notification.is_archived.is_(False),
    ).update({"is_archived": True})

    ninety_days_ago = datetime.utcnow() - timedelta(days=delete_days)
    db.query(notification_models.Notification).filter(
        notification_models.Notification.created_at < ninety_days_ago,
        notification_models.Notification.is_archived.is_(True),
    ).update({"is_deleted": True})

    db.commit()


def process_scheduled_notifications_task(
    db: Session, enqueue_delivery: Callable[[int], None]
) -> None:
    """Enqueue notifications that reached their scheduled delivery time."""
    now = datetime.utcnow()
    scheduled_notifications = (
        db.query(notification_models.Notification)
        .filter(
            notification_models.Notification.scheduled_for <= now,
            notification_models.Notification.is_delivered.is_(False),
        )
        .all()
    )
    for notification in scheduled_notifications:
        enqueue_delivery(notification.id)
        notification.is_delivered = True
    db.commit()


def deliver_notification_task(
    db: Session,
    notification_id: int,
    email_sender: Callable[[notification_models.Notification], None],
    push_sender: Callable[[int], None],
) -> None:
    """Route notification delivery to the configured channels."""
    notification = db.query(notification_models.Notification).get(notification_id)
    if not notification:
        return

    user_prefs = (
        db.query(notification_models.NotificationPreferences)
        .filter(notification_models.NotificationPreferences.user_id == notification.user_id)
        .first()
    )
    if not user_prefs:
        return

    if user_prefs.email_notifications and notification.user and notification.user.email:
        try:
            email_sender(notification)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to queue email notification %s: %s", notification.id, exc)
    if user_prefs.push_notifications:
        push_sender(notification.id)


def send_push_notification_task(db: Session, notification_id: int) -> None:
    """Send a push notification via Firebase for active devices."""
    notification = db.query(notification_models.Notification).get(notification_id)
    if not notification:
        return

    devices = (
        db.query(legacy_models.UserDevice)
        .filter(
            legacy_models.UserDevice.user_id == notification.user_id,
            legacy_models.UserDevice.is_active.is_(True),
        )
        .all()
    )
    for device in devices:
        message = messaging.Message(
            notification=messaging.Notification(
                title="New Notification", body=notification.content
            ),
            data={
                "notification_id": str(notification.id),
                "type": notification.notification_type,
                "link": notification.link or "",
            },
            token=device.fcm_token,
        )
        try:
            messaging.send(message)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error sending push notification: %s", exc)
    db.commit()


__all__ = [
    "cleanup_old_notifications_task",
    "process_scheduled_notifications_task",
    "deliver_notification_task",
    "send_push_notification_task",
]

