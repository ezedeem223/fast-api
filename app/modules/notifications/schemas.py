"""Pydantic schemas dedicated to the notifications domain."""

from __future__ import annotations

from datetime import datetime, date, time
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class NotificationPreferencesUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    categories_preferences: Optional[Dict[str, bool]] = None
    notification_frequency: Optional[str] = None


class NotificationPreferencesOut(BaseModel):
    id: int
    user_id: int
    email_notifications: bool
    push_notifications: bool
    in_app_notifications: bool
    quiet_hours_start: Optional[time]
    quiet_hours_end: Optional[time]
    categories_preferences: Dict[str, bool]
    notification_frequency: str
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class NotificationBase(BaseModel):
    content: str
    notification_type: str
    priority: Any
    category: Any


class NotificationCreate(NotificationBase):
    user_id: int
    link: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None
    notification_channel: Optional[str] = "in_app"
    importance_level: Optional[int] = 1


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_archived: Optional[bool] = None
    interaction_count: Optional[int] = None


class NotificationDeliveryStatus(BaseModel):
    success: bool
    channel: str
    timestamp: datetime
    error_message: Optional[str] = None


class NotificationStatistics(BaseModel):
    total_count: int
    unread_count: int
    categories_distribution: List[Tuple[str, int]]
    priorities_distribution: List[Tuple[str, int]]
    daily_notifications: List[Tuple[date, int]]


class NotificationAnalytics(BaseModel):
    engagement_rate: float
    response_time: float
    peak_activity_hours: List[Dict[str, Union[int, int]]]
    most_interacted_types: List[Dict[str, Union[str, int]]]


class NotificationAnalyticsOut(NotificationAnalytics):
    """Wrapper for analytics output."""

    pass


class NotificationGroupOut(BaseModel):
    id: int
    group_type: str
    count: int
    last_updated: datetime
    sample_notification: "NotificationOut"

    model_config = ConfigDict(from_attributes=True)


class NotificationDeliveryLogOut(BaseModel):
    id: int
    attempt_time: datetime
    status: str
    error_message: Optional[str]
    delivery_channel: str

    model_config = ConfigDict(from_attributes=True)


# Alias for router compatibility
DeliveryLogOut = NotificationDeliveryLogOut


class NotificationWithLogs(BaseModel):
    delivery_logs: List[NotificationDeliveryLogOut]
    retry_count: int
    status: Any
    last_retry: Optional[datetime] = None


class NotificationOut(BaseModel):
    id: int
    content: str
    notification_type: str
    priority: Any
    category: Any
    link: Optional[str]
    is_read: bool
    is_archived: bool
    read_at: Optional[datetime]
    created_at: datetime
    group: Optional[NotificationGroupOut]
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("notification_metadata", "metadata"),
    )

    model_config = ConfigDict(from_attributes=True)


class NotificationSummary(BaseModel):
    unread_count: int
    unseen_count: int
    unread_urgent_count: int
    last_unread_at: Optional[datetime]
    generated_at: datetime


class NotificationFeedResponse(BaseModel):
    notifications: List[NotificationOut]
    unread_count: int
    unseen_count: int
    next_cursor: Optional[int]
    has_more: bool
    last_seen_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PushNotification(BaseModel):
    device_token: str
    title: str
    content: str
    extra_data: Dict[str, Any] = Field(default_factory=dict)


# --- New Request Models required by Router ---


class BulkNotificationRequest(BaseModel):
    user_ids: List[int]
    content: str
    notification_type: str = "system"
    category: str = "info"
    priority: str = "normal"


class ScheduleNotificationRequest(BaseModel):
    user_id: int
    content: str
    scheduled_for: datetime
    notification_type: str = "system"
    category: str = "info"
    priority: str = "normal"


class DeviceTokenRequest(BaseModel):
    device_token: str
    device_type: str = "android"  # or 'ios', 'web'


__all__ = [
    "NotificationPreferencesUpdate",
    "NotificationPreferencesOut",
    "NotificationBase",
    "NotificationCreate",
    "NotificationUpdate",
    "NotificationDeliveryStatus",
    "NotificationStatistics",
    "NotificationAnalytics",
    "NotificationAnalyticsOut",
    "NotificationGroupOut",
    "NotificationDeliveryLogOut",
    "DeliveryLogOut",
    "NotificationWithLogs",
    "NotificationOut",
    "NotificationSummary",
    "NotificationFeedResponse",
    "PushNotification",
    "BulkNotificationRequest",
    "ScheduleNotificationRequest",
    "DeviceTokenRequest",
]
