"""Pydantic schemas dedicated to the notifications domain."""

from __future__ import annotations

from datetime import datetime, date, time
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict


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
    metadata: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "NotificationPreferencesUpdate",
    "NotificationPreferencesOut",
    "NotificationBase",
    "NotificationCreate",
    "NotificationUpdate",
    "NotificationDeliveryStatus",
    "NotificationStatistics",
    "NotificationAnalytics",
    "NotificationGroupOut",
    "NotificationDeliveryLogOut",
    "NotificationWithLogs",
    "NotificationOut",
]
