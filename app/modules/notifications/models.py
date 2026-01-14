"""SQLAlchemy models and enums for the notifications domain.

Notes:
- JSONB columns use a SQLite-safe variant so local tests do not break.
- Status/retry fields capture delivery lifecycle without assuming a specific worker backend.
- Grouping is kept optional to allow batching/aggregation without forcing all notifications into a group.
"""

from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Time
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default


def _jsonb_type():
    """
    Return a JSONB type that gracefully falls back to JSON on SQLite.
    """
    return PG_JSONB().with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


class NotificationStatus(str, enum.Enum):
    """Enumeration for NotificationStatus."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    PERMANENTLY_FAILED = "permanently_failed"


class NotificationPriority(str, enum.Enum):
    """SQLAlchemy model for NotificationPriority."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationCategory(str, enum.Enum):
    """SQLAlchemy model for NotificationCategory."""
    SYSTEM = "system"
    SOCIAL = "social"
    SECURITY = "security"
    PROMOTIONAL = "promotional"
    COMMUNITY = "community"


class NotificationType(str, enum.Enum):
    """Enumeration for NotificationType."""
    NEW_FOLLOWER = "new_follower"
    NEW_COMMENT = "new_comment"
    NEW_REACTION = "new_reaction"
    NEW_MESSAGE = "new_message"
    MENTION = "mention"
    POST_SHARE = "post_share"
    COMMUNITY_INVITE = "community_invite"
    REPORT_UPDATE = "report_update"
    ACCOUNT_SECURITY = "account_security"
    SYSTEM_UPDATE = "system_update"


class NotificationPreferences(Base):
    """Per-user channel toggles, quiet hours, and per-category overrides (JSON for forward compatibility)."""

    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    in_app_notifications = Column(Boolean, default=True)
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    categories_preferences = Column(_jsonb_type(), default={})
    notification_frequency = Column(String, default="realtime")
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())

    user = relationship("User", back_populates="notification_preferences")


class NotificationGroup(Base):
    """Group similar notifications together for batching; `sample_notification_id` aids previews/analytics."""

    __tablename__ = "notification_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_type = Column(String, nullable=False)
    last_updated = Column(DateTime(timezone=True), server_default=timestamp_default())
    count = Column(Integer, default=1)
    sample_notification_id = Column(
        Integer,
        ForeignKey(
            "notifications.id",
            use_alter=True,
            name="fk_notification_groups_sample_notification_id",
        ),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    notifications = relationship(
        "Notification", back_populates="group", foreign_keys="[Notification.group_id]"
    )


class Notification(Base):
    """Notification entity.

    Stores channel, priority, and per-delivery tracking. Retry fields (`retry_strategy`, `max_retries`,
    `current_retry_count`, `last_retry_timestamp`) allow idempotent workers to decide backoff independently.
    `notification_metadata`/`custom_data` are flexible payloads for clients without strict schema coupling.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(String, nullable=False)
    link = Column(String)
    notification_type = Column(String)
    priority = Column(SAEnum(NotificationPriority), default=NotificationPriority.MEDIUM)
    category = Column(SAEnum(NotificationCategory), default=NotificationCategory.SYSTEM)
    is_read = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    related_id = Column(Integer)
    # Flexible payloads for clients/analytics without schema churn.
    notification_metadata = Column(_jsonb_type(), default={})
    group_id = Column(Integer, ForeignKey("notification_groups.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())
    status = Column(SAEnum(NotificationStatus), default=NotificationStatus.PENDING)
    retry_count = Column(Integer, default=0)
    last_retry = Column(DateTime(timezone=True), nullable=True)
    notification_version = Column(Integer, default=1)
    importance_level = Column(Integer, default=1)
    seen_at = Column(DateTime(timezone=True), nullable=True)
    interaction_count = Column(Integer, default=0)
    custom_data = Column(_jsonb_type(), default={})
    device_info = Column(_jsonb_type(), nullable=True)
    notification_channel = Column(String, default="in_app")
    failure_reason = Column(String, nullable=True)
    batch_id = Column(String, nullable=True)
    priority_level = Column(Integer, default=1)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    delivery_tracking = Column(_jsonb_type(), default={})
    # Retry/backoff settings used by workers and schedulers.
    retry_strategy = Column(String, nullable=True)
    max_retries = Column(Integer, default=3)
    current_retry_count = Column(Integer, default=0)
    last_retry_timestamp = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications")
    group = relationship(
        "NotificationGroup", back_populates="notifications", foreign_keys=[group_id]
    )
    analytics = relationship(
        "NotificationAnalytics", back_populates="notification", uselist=False
    )
    delivery_logs = relationship(
        "NotificationDeliveryLog", back_populates="notification"
    )
    delivery_attempts_rel = relationship(
        "NotificationDeliveryAttempt", back_populates="notification"
    )

    __table_args__ = (
        Index("idx_notifications_user_created", "user_id", "created_at"),
        Index("idx_notifications_type", "notification_type"),
        Index("idx_notifications_status", "status"),
    )

    def should_retry(self) -> bool:
        """Return True if notification should be retried based on status, retries, and expiry."""
        if self.status != NotificationStatus.FAILED:
            return False
        if self.current_retry_count >= self.max_retries:
            return False
        from datetime import datetime, timezone

        if self.expiration_date and datetime.now(timezone.utc) > self.expiration_date:
            return False
        return True

    def get_next_retry_delay(self) -> int:
        """Compute delay until next retry attempt."""
        if self.retry_strategy == "exponential":
            return 300 * (2**self.current_retry_count)
        return 300


class NotificationDeliveryAttempt(Base):
    """Delivery attempt audit trail."""

    __tablename__ = "notification_delivery_attempts"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    attempt_number = Column(Integer, nullable=False)
    attempt_time = Column(DateTime(timezone=True), server_default=timestamp_default())
    status = Column(String, nullable=False)
    error_message = Column(String, nullable=True)
    delivery_channel = Column(String, nullable=False)
    response_time = Column(Float)
    attempt_metadata = Column(_jsonb_type(), default={})

    notification = relationship("Notification", back_populates="delivery_attempts_rel")

    __table_args__ = (
        Index(
            "idx_delivery_attempts_notification", "notification_id", "attempt_number"
        ),
    )


class NotificationAnalytics(Base):
    """Aggregated analytics for a notification."""

    __tablename__ = "notification_analytics"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    delivery_attempts = Column(Integer, default=0)
    first_delivery_attempt = Column(
        DateTime(timezone=True), server_default=timestamp_default()
    )
    last_delivery_attempt = Column(
        DateTime(timezone=True), onupdate=timestamp_default()
    )
    successful_delivery = Column(Boolean, default=False)
    delivery_channel = Column(String)
    device_info = Column(_jsonb_type(), default={})
    performance_metrics = Column(_jsonb_type(), default={})

    notification = relationship("Notification", back_populates="analytics")

    __table_args__ = (
        Index("idx_notification_analytics_notification_id", "notification_id"),
        Index("idx_notification_analytics_successful_delivery", "successful_delivery"),
    )


class NotificationDeliveryLog(Base):
    """Delivery log entry."""

    __tablename__ = "notification_delivery_logs"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    attempt_time = Column(DateTime(timezone=True), server_default=timestamp_default())
    status = Column(String)
    error_message = Column(String, nullable=True)
    delivery_channel = Column(String)

    notification = relationship("Notification", back_populates="delivery_logs")


__all__ = [
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
]
