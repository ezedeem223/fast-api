"""Compatibility facade for the modularised notifications domain.

This module re-exports the new package structure so existing imports keep
functioning while the refactor is rolled out incrementally.
"""

from typing import Union

from app.modules.notifications.common import (
    logger,
    notification_cache,
    delivery_status_cache,
    priority_notification_cache,
    get_model_by_id,
    get_or_create,
    handle_async_errors,
)
from app.modules.notifications.email import (
    queue_email_notification,
    schedule_email_notification,
    send_email_notification,
    schedule_email_notification_by_id,
    send_mention_notification,
    send_login_notification,
)
from app.modules.notifications.realtime import (
    ConnectionManager,
    manager,
)
from app.modules.notifications.batching import NotificationBatcher
from app.modules.notifications.analytics import NotificationAnalyticsService
from app.modules.notifications.service import (
    NotificationService,
    NotificationDeliveryManager,
    NotificationRetryHandler,
    CommentNotificationHandler,
    MessageNotificationHandler,
    NotificationManager,
    deliver_scheduled_notification,
    send_bulk_notifications,
    create_notification,
)


@handle_async_errors
async def send_real_time_notification(user_id: int, message: Union[str, dict]):
    """Send a real-time notification via the re-exported connection manager."""
    payload = (
        {"message": message, "type": "simple_notification"}
        if isinstance(message, str)
        else message
    )
    await manager.send_personal_message(payload, user_id)
    logger.info("Real-time notification sent to user %s", user_id)


__all__ = [
    "logger",
    "notification_cache",
    "delivery_status_cache",
    "priority_notification_cache",
    "get_model_by_id",
    "get_or_create",
    "handle_async_errors",
    "queue_email_notification",
    "schedule_email_notification",
    "send_email_notification",
    "schedule_email_notification_by_id",
    "send_mention_notification",
    "send_login_notification",
    "ConnectionManager",
    "manager",
    "send_real_time_notification",
    "NotificationBatcher",
    "NotificationService",
    "NotificationDeliveryManager",
    "NotificationRetryHandler",
    "CommentNotificationHandler",
    "MessageNotificationHandler",
    "NotificationManager",
    "deliver_scheduled_notification",
    "send_bulk_notifications",
    "create_notification",
    "NotificationAnalyticsService",
    "NotificationAnalytics",
]

# Backwards compatibility alias
NotificationAnalytics = NotificationAnalyticsService
