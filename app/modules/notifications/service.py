"""Core notification services, delivery management, and handlers.

Responsibilities:
- Persist and deliver notifications across email/push/realtime channels.
- Enforce user preferences, retries, metadata limits, and caching/idempotency guards.
- Bridge to external WS gateway via optional Redis pub/sub fan-out.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi_mail import MessageSchema
from sqlalchemy.orm import Session

from app import models as legacy_models
from app import schemas
from app.core.config import settings
from app.core.database import get_db
from app.firebase_config import send_multicast_notification
from app.i18n import detect_language, translate_text
from app.modules.notifications import models as notification_models
from app.modules.utils.translation import get_translated_content
from fastapi import BackgroundTasks, HTTPException

from .batching import NotificationBatcher
from .common import (
    delivery_status_cache,
    get_model_by_id,
    handle_async_errors,
    logger,
    notification_cache,
    priority_notification_cache,
)
from .email import send_email_notification
from .realtime import manager
from .repository import NotificationRepository

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

_redis_client = None


def _publish_realtime_broadcast(message: dict) -> None:
    """Optional Redis fan-out for external WS gateway; best-effort."""
    global _redis_client
    url = os.getenv("REALTIME_REDIS_URL")
    channel = os.getenv("REALTIME_REDIS_CHANNEL", "realtime:broadcast")
    if not url or not redis:
        return
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(url)
        except Exception:
            _redis_client = False
    if not _redis_client:
        return
    try:
        _redis_client.publish(channel, json.dumps(message))
    except Exception:
        pass


MAX_METADATA_BYTES = 2048


class NotificationDeliveryManager:
    """Manage delivery of notifications with retries, caching, and fan-out helpers."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 5
        self.retry_delays = [300, 600, 1200, 2400, 4800]  # Delays in seconds
        self.error_tracking: Dict[int, Dict[str, Any]] = {}
        self.batcher = NotificationBatcher()

    async def deliver_notification(
        self, notification: notification_models.Notification
    ) -> bool:
        """Deliver a notification with retry tracking and caching (idempotent per notification id)."""
        previous_metadata = {}
        if hasattr(notification, "notification_metadata") and isinstance(
            notification.notification_metadata, dict
        ):
            previous_metadata = notification.notification_metadata.copy()
        try:
            delivery_key = f"delivery_{notification.id}"
            if getattr(notification, "retry_count", 0) > 0:
                delivery_status_cache.pop(delivery_key, None)
            cached_result = delivery_status_cache.get(delivery_key)
            if cached_result is not None:
                # Avoid double-delivery when the same notification is processed concurrently.
                return cached_result

            user_prefs = self._get_user_preferences(notification.user_id)
            content = await self._process_language(
                notification.content, notification.language, user_prefs
            )
            delivery_tasks = []
            if user_prefs.email_notifications:
                delivery_tasks.append(
                    self._send_email_notification(notification, content)
                )
            if user_prefs.push_notifications:
                delivery_tasks.append(
                    self._send_push_notification(notification, content)
                )
            if user_prefs.in_app_notifications:
                delivery_tasks.append(
                    self._send_realtime_notification(notification, content)
                )
            if not delivery_tasks:
                logger.warning(
                    "No delivery channels enabled for user %s", notification.user_id
                )
                # Leave status as-is (pending) and do not schedule retries when there are no channels.
                self.db.commit()
                return False
            results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            success = all(not isinstance(r, Exception) for r in results)
            await self._update_delivery_status(notification, success, results)
            delivery_status_cache[delivery_key] = success
            return success
        except Exception as exc:
            error_details = {
                "notification_id": notification.id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            logger.error("Delivery error: %s", error_details)
            self.error_tracking[notification.id] = error_details
            delivery_status_cache[delivery_key] = False
            self.db.rollback()
            # Mark the in-memory object as failed by default; retry flow can overwrite.
            notification.status = notification_models.NotificationStatus.FAILED
            notification.failure_reason = json.dumps(error_details)
            # Restore metadata to its previous state so retries don't lose data after rollback.
            if previous_metadata:
                notification.notification_metadata = previous_metadata

            if notification.retry_count + 1 >= self.max_retries:
                await self._handle_final_failure(notification, error_details)
                return False

            if notification.retry_count < self.max_retries:
                await self._schedule_retry(notification)
                return False
            # Fallback persistence if no retry path executes.
            self.db.commit()
            return False

    async def _process_language(
        self,
        content: str,
        current_language: str,
        user_prefs: notification_models.NotificationPreferences,
    ) -> str:
        """Translate content according to user preferences if required."""
        if (
            user_prefs.auto_translate
            and user_prefs.preferred_language != current_language
        ):
            return await get_translated_content(
                content, user_prefs.preferred_language, current_language
            )
        return content

    async def _update_delivery_status(
        self,
        notification: notification_models.Notification,
        success: bool,
        results: List[Any],
    ) -> None:
        """Persist delivery status in the database."""
        status_val = (
            notification_models.NotificationStatus.DELIVERED
            if success
            else notification_models.NotificationStatus.FAILED
        )
        delivery_log = notification_models.NotificationDeliveryLog(
            notification_id=notification.id,
            status=status_val.value,
            error_message=str(results) if not success else None,
            delivery_channel="all",
        )
        notification.status = status_val
        self.db.add(delivery_log)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _get_user_preferences(
        self, user_id: int
    ) -> notification_models.NotificationPreferences:
        """Return cached or freshly fetched notification preferences."""
        cache_key = f"user_prefs_{user_id}"
        if cache_key in notification_cache:
            return notification_cache[cache_key]
        prefs = (
            self.db.query(notification_models.NotificationPreferences)
            .filter(notification_models.NotificationPreferences.user_id == user_id)
            .first()
        )
        if not prefs:
            prefs = notification_models.NotificationPreferences(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
            self.db.refresh(prefs)
        notification_cache[cache_key] = prefs
        return prefs

    async def _send_email_notification(
        self, notification: notification_models.Notification, content: str
    ) -> None:
        """Send notification via email."""
        try:
            user = (
                self.db.query(legacy_models.User)
                .filter(legacy_models.User.id == notification.user_id)
                .first()
            )
            if not user or not user.email:
                logger.warning("No email found for user %s", notification.user_id)
                return
            message = MessageSchema(
                subject=f"{notification.notification_type.replace('_', ' ').title()}",
                recipients=[user.email],
                body=self._create_email_template(notification),
                subtype="html",
            )
            if self.background_tasks:
                self.background_tasks.add_task(send_email_notification, message)
            else:
                await send_email_notification(message)
            logger.info("Email sent to %s", user.email)
        except Exception as exc:
            logger.error("Error sending email notification: %s", exc)

    async def _send_push_notification(
        self, notification: notification_models.Notification, content: str
    ) -> None:
        """Send notification as push message."""
        try:
            user_devices = (
                self.db.query(legacy_models.UserDevice)
                .filter(
                    legacy_models.UserDevice.user_id == notification.user_id,
                    legacy_models.UserDevice.is_active.is_(True),
                )
                .all()
            )
            if not user_devices:
                logger.info("No active devices for user %s", notification.user_id)
                return
            tokens = [device.fcm_token for device in user_devices]
            response = send_multicast_notification(
                tokens=tokens,
                title=notification.notification_type.replace("_", " ").title(),
                body=content,
                data={
                    "notification_id": str(notification.id),
                    "type": notification.notification_type,
                    "link": notification.link or "",
                    "priority": notification.priority.value,
                    "category": notification.category.value,
                },
            )
            if response and hasattr(response, "success_count"):
                logger.info("Push sent to %s devices", response.success_count)
        except Exception as exc:
            logger.error("Error sending push notification: %s", exc)

    async def _send_realtime_notification(
        self, notification: notification_models.Notification, content: str
    ) -> None:
        """Send notification over WebSocket in real time."""
        try:
            message = {
                "type": "notification",
                "data": {
                    "id": notification.id,
                    "content": notification.content,
                    "notification_type": notification.notification_type,
                    "priority": notification.priority.value,
                    "category": notification.category.value,
                    "link": notification.link,
                    "created_at": notification.created_at.isoformat(),
                    "metadata": notification.metadata,
                },
            }
            await manager.send_personal_message(message, notification.user_id)
            _publish_realtime_broadcast(message)
        except Exception as exc:
            logger.error("Error sending realtime notification: %s", exc)

    async def _schedule_retry(
        self, notification: notification_models.Notification
    ) -> None:
        """Queue a retry for a failed notification."""
        retry_delay = self.retry_delays[notification.retry_count]
        notification.retry_count += 1
        notification.status = notification_models.NotificationStatus.RETRYING
        notification.next_retry = datetime.now(timezone.utc) + timedelta(
            seconds=retry_delay
        )
        self.db.commit()
        if self.background_tasks:
            self.background_tasks.add_task(
                self.retry_delivery, notification.id, retry_delay
            )

    async def retry_delivery(self, notification_id: int, delay: int) -> None:
        """Retry delivering a notification after the specified delay."""
        await asyncio.sleep(delay)
        notification = get_model_by_id(
            self.db, notification_models.Notification, notification_id
        )
        if (
            not notification
            or notification.status != notification_models.NotificationStatus.RETRYING
        ):
            return
        success = await self.deliver_notification(notification)
        notification.status = (
            notification_models.NotificationStatus.DELIVERED
            if success
            else notification_models.NotificationStatus.FAILED
        )
        self.db.commit()

    async def _handle_final_failure(
        self,
        notification: notification_models.Notification,
        error_details: Dict[str, Any],
    ) -> None:
        """Persist failure information when retries are exhausted."""
        notification.status = notification_models.NotificationStatus.FAILED
        notification.failure_reason = json.dumps(error_details)
        # Align retry counters so downstream logic sees the failure as terminal.
        notification.retry_count = notification.retry_count or 0
        notification.last_retry = datetime.now(timezone.utc)
        self.db.add(notification)
        self.db.commit()
        try:
            self.db.refresh(notification)
        except Exception:
            # Refresh may fail on SQLite with expired objects; the commit above is sufficient.
            pass

    def _create_email_template(
        self, notification: notification_models.Notification
    ) -> str:
        """Return formatted HTML email template for a notification."""
        return f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    .notification-container {{ padding: 20px; background-color: #f5f5f5; border-radius: 5px; margin: 20px auto; max-width: 600px; }}
                    .notification-title {{ color: #333; margin-bottom: 15px; }}
                    .notification-content {{ color: #666; margin-bottom: 20px; }}
                    .notification-link {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; }}
                    .notification-footer {{ margin-top: 20px; font-size: 0.9em; color: #999; }}
                </style>
            </head>
            <body>
                <div class="notification-container">
                    <h2 class="notification-title">{notification.notification_type.replace('_', ' ').title()}</h2>
                    <div class="notification-content">{notification.content}</div>
                    {f'<a href="{notification.link}" class="notification-link">View Details</a>' if notification.link else ''}
                    <div class="notification-footer">This notification was sent from {settings.SITE_NAME}</div>
                </div>
            </body>
        </html>
        """


class NotificationService:
    """High-level service integrating preference checks and delivery orchestration."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 3
        self.retry_delay = 300
        self.repository = NotificationRepository(db)
        self.delivery_manager = NotificationDeliveryManager(db, background_tasks)

    async def create_notification(
        self,
        user_id: int,
        content: str,
        notification_type: str,
        priority: notification_models.NotificationPriority = notification_models.NotificationPriority.MEDIUM,
        category: notification_models.NotificationCategory = notification_models.NotificationCategory.SYSTEM,
        link: Optional[str] = None,
        related_id: Optional[int] = None,
        metadata: Optional[dict] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> Optional[notification_models.Notification]:
        """Persist notification entry and deliver immediately or schedule."""
        try:
            cache_key = f"category_pref_{user_id}_{category.value}"
            priority_notification_cache.pop(cache_key, None)
            validated_metadata = self._normalize_metadata(metadata)
            user_prefs = self._get_user_preferences(user_id)
            if not self._should_send_notification(user_prefs, category):
                logger.info("Notification skipped for user %s per preferences", user_id)
                return None
            detected_lang = detect_language(content)
            content = await self._process_language(content, detected_lang, user_prefs)
            group = self._find_or_create_group(notification_type, user_id, related_id)
            new_notification = self.repository.create_notification(
                user_id=user_id,
                content=content,
                notification_type=notification_type,
                priority=priority,
                category=category,
                link=link,
                related_id=related_id,
                notification_metadata=validated_metadata,
                scheduled_for=scheduled_for,
                group_id=group.id if group else None,
            )
            if scheduled_for and scheduled_for > datetime.now(timezone.utc):
                self._schedule_delivery(new_notification)
            else:
                # Clear any stale cached delivery result for this notification id before delivering.
                delivery_status_cache.pop(f"delivery_{new_notification.id}", None)
                delivered = await self.deliver_notification(new_notification)
                if (
                    delivered is False
                    and new_notification.status
                    == notification_models.NotificationStatus.PENDING
                ):
                    new_notification.status = (
                        notification_models.NotificationStatus.FAILED
                    )
                    self.db.commit()
            logger.info("Notification created for user %s", user_id)
            return new_notification
        except Exception as exc:
            logger.error("Error creating notification: %s", exc)
            self.db.rollback()
            raise

    def _normalize_metadata(self, metadata: Optional[dict]) -> dict:
        """Validate metadata size and JSON-serializability, defaulting to empty dict."""
        if not metadata:
            return {}
        try:
            encoded = json.dumps(metadata).encode("utf-8")
        except (TypeError, ValueError):
            logger.warning(
                "Invalid notification metadata provided; defaulting to empty metadata."
            )
            return {}
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError("metadata too large")
        return metadata.copy()

    async def deliver_notification(
        self, notification: notification_models.Notification
    ) -> bool:
        """Deliver notification respecting user preferences."""
        return await self.delivery_manager.deliver_notification(notification)

    async def _process_language(
        self,
        content: str,
        current_language: str,
        user_prefs: notification_models.NotificationPreferences,
    ) -> str:
        """Translate content if user requested automatic translation."""
        auto_translate = getattr(user_prefs, "auto_translate", False)
        preferred_language = getattr(user_prefs, "preferred_language", current_language)
        if auto_translate and preferred_language != current_language:
            translated = translate_text(
                content,
                source_lang=current_language,
                target_lang=preferred_language,
            )
            if translated:
                return translated
        return content

    def _get_user_preferences(
        self, user_id: int
    ) -> notification_models.NotificationPreferences:
        """Retrieve or create notification preferences."""
        cache_key = f"user_prefs_{user_id}"
        if cache_key in notification_cache:
            return notification_cache[cache_key]
        prefs = self.repository.ensure_preferences(user_id)
        notification_cache[cache_key] = prefs
        return prefs

    def _should_send_notification(
        self,
        prefs: notification_models.NotificationPreferences,
        category: notification_models.NotificationCategory,
    ) -> bool:
        """Determine if the notification should be emitted based on quiet hours/category/channel toggles."""
        current_time = datetime.now().time()
        if (
            prefs.quiet_hours_start
            and prefs.quiet_hours_end
            and prefs.quiet_hours_start <= current_time <= prefs.quiet_hours_end
        ):
            return False
        # Require at least one channel enabled (email, push, or in-app) before filtering by category.
        if not (
            prefs.email_notifications
            or prefs.push_notifications
            or prefs.in_app_notifications
        ):
            return False
        cache_key = f"category_pref_{prefs.user_id}_{category.value}"
        if cache_key in priority_notification_cache:
            return priority_notification_cache[cache_key]
        category_enabled = prefs.categories_preferences.get(category.value, True)
        priority_notification_cache[cache_key] = category_enabled
        return category_enabled

    def _find_or_create_group(
        self, notification_type: str, user_id: int, related_id: Optional[int]
    ) -> Optional[notification_models.NotificationGroup]:
        """Group notifications of the same type for summarisation."""
        try:
            existing_group = (
                self.db.query(notification_models.NotificationGroup)
                .filter(
                    notification_models.NotificationGroup.group_type
                    == notification_type,
                    notification_models.NotificationGroup.user_id == user_id,
                    notification_models.NotificationGroup.related_id == related_id,
                )
                .first()
            )
            if existing_group:
                existing_group.count += 1
                existing_group.last_updated = datetime.now(timezone.utc)
                self.db.commit()
                return existing_group
            new_group = notification_models.NotificationGroup(
                group_type=notification_type,
                user_id=user_id,
                related_id=related_id,
                slug=str(uuid.uuid4()),
            )
            self.db.add(new_group)
            self.db.commit()
            self.db.refresh(new_group)
            return new_group
        except Exception as exc:
            logger.error("Error in grouping: %s", exc)
            self.db.rollback()
            return None

    def _schedule_delivery(
        self, notification: notification_models.Notification
    ) -> None:
        """Register a background task to deliver scheduled notifications."""
        if self.background_tasks and notification.scheduled_for:
            self.background_tasks.add_task(
                deliver_scheduled_notification,
                notification.id,
                notification.scheduled_for,
            )
            logger.info(
                "Scheduled notification %s for %s",
                notification.id,
                notification.scheduled_for,
            )

    def build_notifications_query(
        self,
        *,
        user_id: int,
        include_read: bool = False,
        include_archived: bool = False,
        category: Optional[notification_models.NotificationCategory] = None,
        priority: Optional[notification_models.NotificationPriority] = None,
        status: Optional[notification_models.NotificationStatus] = None,
        since: Optional[datetime] = None,
    ):
        """Compose a base query for listing notifications."""
        return self.repository.build_notifications_query(
            user_id=user_id,
            include_read=include_read,
            include_archived=include_archived,
            category=category,
            priority=priority,
            status=status,
            since=since,
        )

    async def execute_query(self, query, skip: int, limit: int):
        """Materialise a notifications query with pagination."""
        return query.offset(skip).limit(limit).all()

    async def get_notification_feed(
        self,
        *,
        user_id: int,
        cursor: Optional[int] = None,
        limit: int = 20,
        include_read: bool = False,
        include_archived: bool = False,
        category: Optional[notification_models.NotificationCategory] = None,
        priority: Optional[notification_models.NotificationPriority] = None,
        status: Optional[notification_models.NotificationStatus] = None,
        mark_seen: bool = True,
        mark_read: bool = False,
    ) -> Dict[str, Any]:
        """Return a cursor-paginated notification feed."""
        base_query = self.build_notifications_query(
            user_id=user_id,
            include_read=include_read,
            include_archived=include_archived,
            category=category,
            priority=priority,
            status=status,
        )
        if cursor:
            base_query = base_query.filter(notification_models.Notification.id < cursor)
        records = base_query.limit(limit + 1).all()
        has_more = len(records) > limit
        notifications = records[:limit]
        next_cursor = notifications[-1].id if has_more else None
        seen_timestamp = (
            self._mark_notifications_seen(notifications, mark_read)
            if mark_seen
            else None
        )
        unread_count = self.repository.unread_count(user_id)
        unseen_count = self.repository.unseen_count(user_id)
        last_seen_at = (
            max((n.seen_at for n in notifications if n.seen_at), default=None)
            if notifications
            else None
        )
        if last_seen_at and last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
        if seen_timestamp and (not last_seen_at or seen_timestamp > last_seen_at):
            last_seen_at = seen_timestamp
        return {
            "notifications": notifications,
            "unread_count": unread_count,
            "unseen_count": unseen_count,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "last_seen_at": last_seen_at,
        }

    async def mark_as_read(self, notification_id: int, user_id: int):
        """Mark a single notification as read."""
        notification = self.repository.mark_notification_as_read(
            notification_id, user_id
        )
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return notification

    async def mark_all_as_read(self, user_id: int) -> Dict[str, int]:
        """Mark every unread notification for the user as read."""
        updated = self.repository.mark_all_as_read(user_id)
        return {"updated": updated}

    async def archive_notification(self, notification_id: int, user_id: int):
        """Archive a notification."""
        notification = self.repository.archive_notification(notification_id, user_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return notification

    async def delete_notification(self, notification_id: int, user_id: int):
        """Soft-delete a notification."""
        notification = self.repository.soft_delete_notification(
            notification_id, user_id
        )
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"deleted": True}

    async def get_user_preferences(self, user_id: int):
        """Expose notification preferences via async API."""
        return self._get_user_preferences(user_id)

    async def update_user_preferences(
        self, user_id: int, preferences: schemas.NotificationPreferencesUpdate
    ):
        """Update notification preferences from a Pydantic payload."""
        prefs = self._get_user_preferences(user_id)
        update_data = preferences.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(prefs, field, value)
        prefs.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(prefs)
        return prefs

    async def get_unread_count(self, user_id: int) -> int:
        """Return the number of unread notifications for a user."""
        return self.repository.unread_count(user_id)

    async def get_unread_summary(self, user_id: int) -> Dict[str, Any]:
        """Return counts that power badge indicators."""
        summary = self.repository.get_unread_summary(user_id)
        summary["generated_at"] = datetime.now(timezone.utc)
        return summary

    def _mark_notifications_seen(
        self,
        notifications: List[notification_models.Notification],
        mark_read: bool,
    ) -> Optional[datetime]:
        """Set seen/read timestamps the first time a notification is fetched."""
        if not notifications:
            return None
        now = datetime.now(timezone.utc)
        should_commit = False
        for notification in notifications:
            updated = False
            if notification.seen_at is None:
                notification.seen_at = now
                updated = True
            if mark_read and not notification.is_read:
                notification.is_read = True
                notification.read_at = now
                updated = True
            if notification.status in (
                notification_models.NotificationStatus.PENDING,
                notification_models.NotificationStatus.RETRYING,
            ):
                notification.status = notification_models.NotificationStatus.DELIVERED
                updated = True
            if updated:
                should_commit = True
        if should_commit:
            self.db.commit()
            return now
        return None

    async def bulk_create_notifications(
        self,
        notifications: List[schemas.NotificationCreate],
    ) -> List[Optional[notification_models.Notification]]:
        """Create a batch of notifications from schema objects."""
        created: List[Optional[notification_models.Notification]] = []
        seen_keys = set()
        try:
            for payload in notifications:
                priority = (
                    payload.priority
                    if isinstance(
                        payload.priority, notification_models.NotificationPriority
                    )
                    else notification_models.NotificationPriority(payload.priority)
                )
                category = (
                    payload.category
                    if isinstance(
                        payload.category, notification_models.NotificationCategory
                    )
                    else notification_models.NotificationCategory(payload.category)
                )
                metadata = self._normalize_metadata(payload.metadata)
                cache_fragment = None
                if payload.metadata:
                    try:
                        cache_fragment = json.dumps(metadata, sort_keys=True)
                    except Exception:
                        cache_fragment = None
                key = (
                    payload.user_id,
                    payload.content,
                    payload.notification_type,
                    priority,
                    category,
                    payload.link,
                    payload.scheduled_for,
                    cache_fragment,
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                prefs = self._get_user_preferences(payload.user_id)
                cache_key = f"category_pref_{payload.user_id}_{category.value}"
                priority_notification_cache.pop(cache_key, None)
                if not self._should_send_notification(prefs, category):
                    created.append(None)
                    continue
                detected_lang = detect_language(payload.content)
                translated_content = await self._process_language(
                    payload.content, detected_lang, prefs
                )
                notification = notification_models.Notification(
                    user_id=payload.user_id,
                    content=translated_content,
                    notification_type=payload.notification_type,
                    priority=priority,
                    category=category,
                    link=payload.link,
                    related_id=None,
                    notification_metadata=metadata,
                    scheduled_for=payload.scheduled_for,
                )
                self.db.add(notification)
                created.append(notification)
            self.db.commit()
            for item in created:
                if item:
                    self.db.refresh(item)
            return created
        except Exception:
            self.db.rollback()
            raise

    async def cleanup_old_notifications(self, days: int) -> int:
        """Remove archived notifications older than the given number of days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self.repository.cleanup_archived(cutoff)

    async def retry_failed_notification(self, notification_id: int) -> bool:
        """Retry a failed notification immediately."""
        notification = get_model_by_id(
            self.db, notification_models.Notification, notification_id
        )
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notification.status != notification_models.NotificationStatus.FAILED:
            return False
        success = await self.delivery_manager.deliver_notification(notification)
        notification.status = (
            notification_models.NotificationStatus.DELIVERED
            if success
            else notification_models.NotificationStatus.FAILED
        )
        notification.retry_count += 1
        notification.last_retry = datetime.now(timezone.utc)
        self.db.commit()
        return success

    async def get_delivery_statistics(self) -> Dict[str, int]:
        """Aggregate delivery statistics across notifications."""
        total = self.repository.delivery_log_total()
        delivered = self.repository.delivery_log_counts("delivered") or 0
        failed = self.repository.delivery_log_counts("failed") or 0
        pending = total - delivered - failed
        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": max(pending, 0),
        }


class NotificationRetryHandler:
    """Handles retrying of failed notifications."""

    def __init__(
        self,
        db: Session,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 3
        self.retry_delays = [300, 600, 1800]  # 5 mins, 10 mins, 30 mins

    async def handle_failed_notification(self, notification_id: int) -> None:
        """Process a failed notification and queue retry if allowed."""
        notification = get_model_by_id(
            self.db, notification_models.Notification, notification_id
        )
        if not notification:
            return
        if notification.retry_count >= self.max_retries:
            notification.status = "permanently_failed"
            self.db.commit()
            return
        delay = self.retry_delays[notification.retry_count]
        notification.retry_count += 1
        notification.status = "retrying"
        notification.next_retry = datetime.now() + timedelta(seconds=delay)
        self.db.commit()
        if self.background_tasks:
            self.background_tasks.add_task(
                self.retry_notification, notification_id, delay
            )

    async def retry_notification(self, notification_id: int, delay: int) -> None:
        """Retry sending the notification after a specified delay."""
        await asyncio.sleep(delay)
        notification = get_model_by_id(
            self.db, notification_models.Notification, notification_id
        )
        if not notification or notification.status != "retrying":
            return
        notification_service = NotificationService(self.db)
        success = await notification_service.deliver_notification(notification)
        notification.status = "delivered" if success else "failed"
        self.db.commit()


class CommentNotificationHandler:
    """Handles notifications triggered by comment activity."""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_comment(
        self, comment: legacy_models.Comment, post: legacy_models.Post
    ):
        """Send notifications for new comments and replies."""
        if comment.owner_id != post.owner_id:
            await self.notification_service.create_notification(
                user_id=post.owner_id,
                content=f"{comment.owner.username} commented on your post",
                notification_type="new_comment",
                priority=notification_models.NotificationPriority.MEDIUM,
                category=notification_models.NotificationCategory.SOCIAL,
                link=f"/post/{post.id}#comment-{comment.id}",
            )
        if comment.parent_id:
            parent_comment = get_model_by_id(
                self.db, legacy_models.Comment, comment.parent_id
            )
            if parent_comment and parent_comment.owner_id != comment.owner_id:
                await self.notification_service.create_notification(
                    user_id=parent_comment.owner_id,
                    content=f"{comment.owner.username} replied to your comment",
                    notification_type="comment_reply",
                    priority=notification_models.NotificationPriority.MEDIUM,
                    category=notification_models.NotificationCategory.SOCIAL,
                    link=f"/post/{post.id}#comment-{comment.id}",
                )


class MessageNotificationHandler:
    """Handles notifications for new messages."""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_message(self, message: legacy_models.Message) -> None:
        """Send notification when new message arrives."""
        user_prefs = (
            self.db.query(notification_models.NotificationPreferences)
            .filter(
                notification_models.NotificationPreferences.user_id
                == message.receiver_id
            )
            .first()
        )
        if not user_prefs or user_prefs.message_notifications:
            await self.notification_service.create_notification(
                user_id=message.receiver_id,
                content=f"New message from {message.sender.username}",
                notification_type="new_message",
                priority=notification_models.NotificationPriority.HIGH,
                category=notification_models.NotificationCategory.SOCIAL,
                link=f"/messages/{message.sender_id}",
                metadata={
                    "sender_id": message.sender_id,
                    "sender_name": message.sender.username,
                    "message_type": message.message_type.value,
                    "conversation_id": message.conversation_id,
                },
            )


class NotificationManager:
    """Utility wrapper used by API endpoints to smoke-test channels."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.service = NotificationService(db, background_tasks)

    async def test_all_channels(self, user_id: int) -> Dict[str, Any]:
        """Create a sample notification and report channels that were exercised."""
        sample_notification = await self.service.create_notification(
            user_id=user_id,
            content="Test notification payload",
            notification_type="test_notification",
            priority=notification_models.NotificationPriority.MEDIUM,
            category=notification_models.NotificationCategory.SYSTEM,
            link="/notifications/test",
        )
        result = {
            "in_app": sample_notification is not None,
            "email_background_task": self.background_tasks is not None,
            "push": False,
        }
        return result


@handle_async_errors
async def deliver_scheduled_notification(
    notification_id: int, scheduled_time: datetime
) -> None:
    """Deliver scheduled notification instances."""
    try:
        db = next(get_db())
        notification_service = NotificationService(db)
        notification = get_model_by_id(
            db, notification_models.Notification, notification_id
        )
        if not notification:
            logger.error("Scheduled notification %s not found", notification_id)
            return
        await notification_service.deliver_notification(notification)
        logger.info("Scheduled notification %s delivered", notification_id)
    finally:
        db.close()


@handle_async_errors
async def send_bulk_notifications(
    user_ids: List[int],
    content: str,
    notification_type: str,
    db: Session,
    background_tasks: BackgroundTasks,
) -> Dict[str, int]:
    """Send a notification to a batch of users."""
    notification_service = NotificationService(db, background_tasks)
    tasks = [
        notification_service.create_notification(
            user_id=user_id,
            content=content,
            notification_type=notification_type,
        )
        for user_id in user_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for result in results if not isinstance(result, Exception))
    logger.info("Bulk notifications: %s successful of %s", success_count, len(user_ids))
    return {
        "total": len(user_ids),
        "successful": success_count,
        "failed": len(user_ids) - success_count,
    }


def create_notification(
    db: Session,
    user_id: int,
    content: str,
    link: str,
    notification_type: str,
    related_id: Optional[int] = None,
) -> notification_models.Notification:
    """Synchronously create a notification record."""
    try:
        new_notification = notification_models.Notification(
            user_id=user_id,
            content=content,
            link=link,
            notification_type=notification_type,
            related_id=related_id,
        )
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)
        logger.info("Notification created for user %s", user_id)
        return new_notification
    except Exception as exc:
        logger.error("Error creating notification: %s", exc)
        db.rollback()
        raise


__all__ = [
    "NotificationDeliveryManager",
    "NotificationService",
    "NotificationRetryHandler",
    "CommentNotificationHandler",
    "MessageNotificationHandler",
    "NotificationManager",
    "deliver_scheduled_notification",
    "send_bulk_notifications",
    "create_notification",
]
