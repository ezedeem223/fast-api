"""Notifications domain package."""

from .analytics import NotificationAnalyticsService
from .batching import NotificationBatcher
from .models import (
    Notification,
    NotificationAnalytics,
    NotificationCategory,
    NotificationDeliveryAttempt,
    NotificationDeliveryLog,
    NotificationGroup,
    NotificationPreferences,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from .realtime import ConnectionManager, manager
from .service import (
    NotificationDeliveryManager,
    NotificationManager,
    NotificationRetryHandler,
    NotificationService,
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
