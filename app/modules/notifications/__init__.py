"""Notifications domain package."""

from .models import (
    NotificationStatus,
    NotificationPriority,
    NotificationCategory,
    NotificationType,
    NotificationPreferences,
    NotificationGroup,
    Notification,
    NotificationDeliveryAttempt,
    NotificationAnalytics,
    NotificationDeliveryLog,
)
from .realtime import ConnectionManager, manager
from .batching import NotificationBatcher
from .analytics import NotificationAnalyticsService
from .service import (
    NotificationService,
    NotificationDeliveryManager,
    NotificationRetryHandler,
    NotificationManager,
)

__all__ = [
    "ConnectionManager",
    "manager",
    "NotificationStatus",
    "NotificationPriority",
    "NotificationCategory",
    "NotificationType",
    "NotificationPreferences",
    "NotificationGroup",
    "Notification",
    "NotificationDeliveryAttempt",
    "NotificationAnalytics",
    "NotificationDeliveryLog",
    "NotificationBatcher",
    "NotificationAnalyticsService",
    "NotificationService",
    "NotificationDeliveryManager",
    "NotificationRetryHandler",
    "NotificationManager",
]
