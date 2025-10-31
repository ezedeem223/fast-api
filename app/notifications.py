"""
File: notifications.py
Description: This module handles the creation, scheduling, batching, and delivery of notifications
via email, push, and real-time (WebSocket). It also includes support for bulk notifications,
analytics, and retry mechanisms.
"""

# ============================================
# Imports and Dependencies
# ============================================
from fastapi import BackgroundTasks, WebSocket, HTTPException
from fastapi_mail import MessageSchema
from pydantic import EmailStr
from typing import List, Union, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import json
import logging
from .database import get_db
from . import models, schemas
from .config import settings, fm
from .firebase_config import send_multicast_notification
from .utils import get_translated_content
import asyncio
from cachetools import TTLCache
from .i18n import translate_text, detect_language
from .models import (
    Notification,
    NotificationDeliveryLog,
    NotificationGroup,
    NotificationAnalytics,
    NotificationStatus,
    NotificationPriority,
    NotificationCategory,
    User,
    NotificationPreferences,
)
import uuid

# ============================================
# Logger Configuration
# ============================================
logger = logging.getLogger(__name__)

# ============================================
# Caches for Notifications
# ============================================
notification_cache = TTLCache(maxsize=1000, ttl=300)
delivery_status_cache = TTLCache(maxsize=5000, ttl=3600)
priority_notification_cache = TTLCache(maxsize=500, ttl=60)  # For urgent notifications


# ============================================
# Common Helper Functions
# ============================================
def get_model_by_id(db: Session, model, id) -> Optional[Any]:
    """
    Retrieves a model instance by its id.
    """
    try:
        return db.query(model).filter(model.id == id).first()
    except Exception as e:
        logger.error(f"Error fetching {model.__name__} with id {id}: {e}")
        return None


def get_or_create(db: Session, model, defaults: dict = None, **kwargs) -> Any:
    """
    Retrieves a model instance matching the given kwargs or creates a new one with defaults.
    """
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    params = kwargs.copy()
    if defaults:
        params.update(defaults)
    instance = model(**params)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def handle_async_errors(func):
    """
    Decorator for async functions to log errors and re-raise them.
    """

    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            raise

    return wrapper


# ============================================
# Email Notification Function
# ============================================
@handle_async_errors
async def send_email_notification(message: MessageSchema) -> None:
    """
    Sends an email notification using the fastapi_mail instance (fm).

    Raises an exception if sending fails.
    """
    await fm.send_message(message)
    logger.info("Email notification sent successfully")


# ============================================
# Schedule Email Notification
# ============================================
def schedule_email_notification(notification_id: int, delay: int = 60):
    """
    Schedules an email notification to be sent after a specified delay (in seconds).

    Uses asyncio.create_task to schedule the task.
    """
    logger.info(
        f"Scheduled email notification {notification_id} to be sent in {delay} seconds."
    )

    async def task():
        await asyncio.sleep(delay)
        db_session = next(get_db())
        try:
            notification = get_model_by_id(
                db_session, models.Notification, notification_id
            )
            if notification:
                user = get_model_by_id(db_session, models.User, notification.user_id)
                if user and user.email:
                    message = MessageSchema(
                        subject=f"Notification: {notification.notification_type.replace('_',' ').title()}",
                        recipients=[user.email],
                        body=notification.content,
                        subtype="html",
                    )
                    await send_email_notification(message)
                    logger.info(
                        f"Scheduled email notification {notification_id} delivered."
                    )
        except Exception as e:
            logger.error(f"Error in scheduled email notification: {e}")
        finally:
            db_session.close()

    asyncio.create_task(task())


# ============================================
# Notification Batch Processor
# ============================================
class NotificationBatcher:
    """Batch processor for notifications."""

    def __init__(self, max_batch_size: int = 100, max_wait_time: float = 1.0):
        self.batch = []
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self._lock = asyncio.Lock()
        self._last_flush = datetime.now(timezone.utc)

    async def add(self, notification: dict) -> None:
        """
        Adds a notification to the batch and flushes if batch size or wait time is reached.
        """
        should_flush = False
        async with self._lock:
            self.batch.append(notification)
            if (
                len(self.batch) >= self.max_batch_size
                or (datetime.now(timezone.utc) - self._last_flush).total_seconds()
                >= self.max_wait_time
            ):
                should_flush = True
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        """
        Flushes the current batch by processing it.
        """
        async with self._lock:
            if not self.batch:
                return
            pending = list(self.batch)
            self.batch = []
            self._last_flush = datetime.now(timezone.utc)
        await self._process_batch(pending)

    async def _process_batch(self, notifications: List[dict]) -> None:
        """
        Processes the batch by grouping notifications by channel and sending them.
        """
        email_notifications = []
        push_notifications = []
        in_app_notifications = []
        for notif in notifications:
            if notif.get("channel") == "email":
                email_notifications.append(notif)
            elif notif.get("channel") == "push":
                push_notifications.append(notif)
            else:
                in_app_notifications.append(notif)
        tasks = []
        if email_notifications:
            tasks.append(self._send_batch_emails(email_notifications))
        if push_notifications:
            tasks.append(self._send_batch_push(push_notifications))
        if in_app_notifications:
            tasks.append(self._send_batch_in_app(in_app_notifications))
        await asyncio.gather(*tasks)

    async def _send_batch_emails(self, notifications: List[dict]) -> None:
        """
        Sends a batch of email notifications grouped by recipient.
        """
        email_groups = {}
        for notif in notifications:
            email = notif["recipient"]
            email_groups.setdefault(email, []).append(notif)
        for email, notifs in email_groups.items():
            message = MessageSchema(
                subject="New Notifications",
                recipients=[email],
                body=self._format_batch_email(notifs),
                subtype="html",
            )
            await send_email_notification(message)

    @staticmethod
    def _format_batch_email(notifications: List[dict]) -> str:
        """
        Formats the batch email body.
        """
        return "\n".join(
            [
                f"<div><h3>{n['title']}</h3><p>{n['content']}</p></div>"
                for n in notifications
            ]
        )


# ============================================
# Notification Delivery Manager
# ============================================
class NotificationDeliveryManager:
    """Manages delivery of notifications with retry support."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 5
        self.retry_delays = [300, 600, 1200, 2400, 4800]  # Delays in seconds
        self.error_tracking = {}
        self.batcher = NotificationBatcher()

    async def deliver_notification(self, notification: models.Notification) -> bool:
        """
        Delivers a notification with retry support and tracks the delivery status.
        """
        try:
            delivery_key = f"delivery_{notification.id}"
            if delivery_key in delivery_status_cache:
                return delivery_status_cache[delivery_key]
            user_prefs = self._get_user_preferences(notification.user_id)
            # Use unified language processing
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
            results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            success = all(not isinstance(r, Exception) for r in results)
            await self._update_delivery_status(notification, success, results)
            delivery_status_cache[delivery_key] = success
            return success
        except Exception as e:
            error_details = {
                "notification_id": notification.id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            logger.error(f"Delivery error: {error_details}")
            self.error_tracking[notification.id] = error_details
            if notification.retry_count < self.max_retries:
                await self._schedule_retry(notification)
            else:
                await self._handle_final_failure(notification, error_details)
            return False

    async def _process_language(
        self,
        content: str,
        current_language: str,
        user_prefs: models.NotificationPreferences,
    ) -> str:
        """
        Unifies language processing for notifications.
        If auto_translate is enabled and the user's preferred language differs from the current language,
        translates the content.
        """
        if (
            user_prefs.auto_translate
            and user_prefs.preferred_language != current_language
        ):
            return await get_translated_content(
                content, user_prefs.preferred_language, current_language
            )
        return content

    async def _update_delivery_status(
        self, notification: models.Notification, success: bool, results: List[Any]
    ) -> None:
        """
        Updates the delivery status of a notification in the database.
        """
        status_val = (
            models.NotificationStatus.DELIVERED
            if success
            else models.NotificationStatus.FAILED
        )
        delivery_log = models.NotificationDeliveryLog(
            notification_id=notification.id,
            status=status_val.value,
            error_message=str(results) if not success else None,
            delivery_channel="all",
        )
        notification.status = status_val
        self.db.add(delivery_log)
        self.db.commit()

    def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
        """
        Retrieves user notification preferences, using caching if available.
        """
        cache_key = f"user_prefs_{user_id}"
        if cache_key in notification_cache:
            return notification_cache[cache_key]
        prefs = (
            self.db.query(models.NotificationPreferences)
            .filter(models.NotificationPreferences.user_id == user_id)
            .first()
        )
        if not prefs:
            prefs = models.NotificationPreferences(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
            self.db.refresh(prefs)
        notification_cache[cache_key] = prefs
        return prefs

    async def _send_email_notification(
        self, notification: models.Notification, content: str
    ) -> None:
        """
        Sends an email notification.
        """
        try:
            user = (
                self.db.query(models.User)
                .filter(models.User.id == notification.user_id)
                .first()
            )
            if not user or not user.email:
                logger.warning(f"No email found for user {notification.user_id}")
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
            logger.info(f"Email sent to {user.email}")
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")

    async def _send_push_notification(
        self, notification: models.Notification, content: str
    ) -> None:
        """
        Sends a push notification.
        """
        try:
            user_devices = (
                self.db.query(models.UserDevice)
                .filter(
                    models.UserDevice.user_id == notification.user_id,
                    models.UserDevice.is_active == True,
                )
                .all()
            )
            if not user_devices:
                logger.info(f"No active devices for user {notification.user_id}")
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
                logger.info(f"Push sent to {response.success_count} devices")
        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}")

    async def _send_realtime_notification(
        self, notification: models.Notification, content: str
    ) -> None:
        """
        Sends a real-time notification via WebSocket.
        """
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
        except Exception as e:
            logger.error(f"Error sending realtime notification: {str(e)}")

    async def _schedule_retry(self, notification: models.Notification) -> None:
        """
        Schedules a retry for a failed notification.
        """
        retry_delay = self.retry_delays[notification.retry_count]
        notification.retry_count += 1
        notification.status = models.NotificationStatus.RETRYING
        notification.next_retry = datetime.now(timezone.utc) + timedelta(
            seconds=retry_delay
        )
        self.db.commit()
        if self.background_tasks:
            self.background_tasks.add_task(
                self.retry_delivery, notification.id, retry_delay
            )

    async def retry_delivery(self, notification_id: int, delay: int) -> None:
        """
        Retries delivering a notification after a specified delay.
        """
        await asyncio.sleep(delay)
        notification = get_model_by_id(self.db, models.Notification, notification_id)
        if (
            not notification
            or notification.status != models.NotificationStatus.RETRYING
        ):
            return
        success = await self.deliver_notification(notification)
        notification.status = (
            models.NotificationStatus.DELIVERED
            if success
            else models.NotificationStatus.FAILED
        )
        self.db.commit()

    async def _handle_final_failure(
        self, notification: models.Notification, error_details: dict
    ) -> None:
        """
        Handles final failure after all retries have been exhausted.
        """
        notification.status = models.NotificationStatus.FAILED
        notification.failure_reason = json.dumps(error_details)
        self.db.commit()

    def _create_email_template(self, notification: models.Notification) -> str:
        """
        Creates an HTML email template for the notification.
        """
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

    def _schedule_delivery(self, notification: models.Notification):
        """
        Schedules the delivery of a notification.
        """
        if self.background_tasks:
            self.background_tasks.add_task(
                deliver_scheduled_notification,
                notification.id,
                notification.scheduled_for,
            )
            logger.info(
                f"Scheduled notification {notification.id} for {notification.scheduled_for}"
            )


# ============================================
# WebSocket Connection Manager
# ============================================
class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    """

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        """
        Accepts and stores a WebSocket connection for a user.
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            logger.info(f"WebSocket connected for user {user_id}")

    async def disconnect(self, websocket: WebSocket, user_id: int):
        """
        Removes a WebSocket connection for a user.
        """
        async with self._lock:
            if (
                user_id in self.active_connections
                and websocket in self.active_connections[user_id]
            ):
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_personal_message(self, message: dict, user_id: int):
        """
        Sends a JSON message to a specific user's active WebSocket connections.
        """
        if user_id in self.active_connections:
            broken_connections = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")
                    broken_connections.append(connection)
            if broken_connections:
                async with self._lock:
                    for connection in broken_connections:
                        if connection in self.active_connections[user_id]:
                            self.active_connections[user_id].remove(connection)

    async def broadcast(self, message: dict):
        """
        Broadcasts a message to all connected users.
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


# ============================================
# Notification Service
# ============================================
class NotificationService:
    """
    Service to handle creation and delivery of notifications.
    """

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 3
        self.retry_delay = 300

    async def create_notification(
        self,
        user_id: int,
        content: str,
        notification_type: str,
        priority: models.NotificationPriority = models.NotificationPriority.MEDIUM,
        category: models.NotificationCategory = models.NotificationCategory.SYSTEM,
        link: Optional[str] = None,
        related_id: Optional[int] = None,
        metadata: Optional[dict] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> Optional[models.Notification]:
        """
        Creates a new notification with smart processing based on user preferences.
        """
        try:
            user_prefs = self._get_user_preferences(user_id)
            if not self._should_send_notification(user_prefs, category):
                logger.info(f"Notification skipped for user {user_id} per preferences")
                return None
            detected_lang = detect_language(content)
            content = await self._process_language(content, detected_lang, user_prefs)
            group = self._find_or_create_group(notification_type, user_id, related_id)
            new_notification = models.Notification(
                user_id=user_id,
                content=content,
                notification_type=notification_type,
                priority=priority,
                category=category,
                link=link,
                related_id=related_id,
                metadata=metadata or {},
                scheduled_for=scheduled_for,
                group_id=group.id if group else None,
                language=detected_lang,
            )
            self.db.add(new_notification)
            self.db.commit()
            self.db.refresh(new_notification)
            if scheduled_for and scheduled_for > datetime.now(timezone.utc):
                self._schedule_delivery(new_notification)
            else:
                await self.deliver_notification(new_notification)
            logger.info(f"Notification created for user {user_id}")
            return new_notification
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            self.db.rollback()
            raise

    async def deliver_notification(self, notification: models.Notification):
        """
        Delivers a notification to the user based on their preferences.
        """
        try:
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
            results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            success = all(not isinstance(r, Exception) for r in results)
            status_val = (
                models.NotificationStatus.DELIVERED
                if success
                else models.NotificationStatus.FAILED
            )
            log = models.NotificationDeliveryLog(
                notification_id=notification.id,
                status=status_val.value,
                error_message=str(results) if not success else None,
                delivery_channel="all",
            )
            self.db.add(log)
            notification.status = status_val
            self.db.commit()
        except Exception as e:
            notification.status = models.NotificationStatus.FAILED
            log = models.NotificationDeliveryLog(
                notification_id=notification.id,
                status="failed",
                error_message=str(e),
                delivery_channel="all",
            )
            self.db.add(log)
            self.db.commit()
            raise

    async def _process_language(
        self,
        content: str,
        current_language: str,
        user_prefs: models.NotificationPreferences,
    ) -> str:
        """
        Unifies language processing for notifications.
        """
        if (
            user_prefs.auto_translate
            and user_prefs.preferred_language != current_language
        ):
            return await get_translated_content(
                content, user_prefs.preferred_language, current_language
            )
        return content

    def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
        """
        Retrieves user notification preferences.
        """
        prefs = (
            self.db.query(models.NotificationPreferences)
            .filter(models.NotificationPreferences.user_id == user_id)
            .first()
        )
        if not prefs:
            prefs = models.NotificationPreferences(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
            self.db.refresh(prefs)
        return prefs

    def _should_send_notification(
        self,
        prefs: models.NotificationPreferences,
        category: models.NotificationCategory,
    ) -> bool:
        """
        Determines if a notification should be sent based on user preferences.
        """
        if not prefs:
            return True
        current_time = datetime.now().time()
        if (
            prefs.quiet_hours_start
            and prefs.quiet_hours_end
            and current_time >= prefs.quiet_hours_start
            and current_time <= prefs.quiet_hours_end
        ):
            return False
        category_enabled = prefs.categories_preferences.get(category.value, True)
        return category_enabled

    def _find_or_create_group(
        self, notification_type: str, user_id: int, related_id: Optional[int] = None
    ) -> Optional[models.NotificationGroup]:
        """
        Finds an existing notification group or creates a new one.
        """
        if notification_type not in {
            "post_like",
            "post_comment",
            "follower",
            "mention",
            "community_post",
            "message_received",
            "post_shared",
        }:
            return None
        try:
            existing_group = (
                self.db.query(models.NotificationGroup)
                .join(models.Notification)
                .filter(
                    and_(
                        models.NotificationGroup.group_type == notification_type,
                        models.Notification.user_id == user_id,
                        models.Notification.created_at
                        >= datetime.now(timezone.utc) - timedelta(hours=24),
                    )
                )
                .first()
            )
            if existing_group:
                existing_group.count += 1
                existing_group.last_updated = datetime.now(timezone.utc)
                self.db.commit()
                return existing_group
            new_group = models.NotificationGroup(group_type=notification_type)
            self.db.add(new_group)
            self.db.commit()
            self.db.refresh(new_group)
            return new_group
        except Exception as e:
            logger.error(f"Error in grouping: {str(e)}")
            self.db.rollback()
            return None

    def _schedule_delivery(self, notification: models.Notification):
        """
        Schedules the delivery of a notification.
        """
        if self.background_tasks:
            self.background_tasks.add_task(
                deliver_scheduled_notification,
                notification.id,
                notification.scheduled_for,
            )
            logger.info(
                f"Scheduled notification {notification.id} for {notification.scheduled_for}"
            )


# ============================================
# WebSocket Connection Manager
# ============================================
class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    """

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        """
        Accepts and stores a WebSocket connection for a user.
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            logger.info(f"WebSocket connected for user {user_id}")

    async def disconnect(self, websocket: WebSocket, user_id: int):
        """
        Removes a WebSocket connection for a user.
        """
        async with self._lock:
            if (
                user_id in self.active_connections
                and websocket in self.active_connections[user_id]
            ):
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_personal_message(self, message: dict, user_id: int):
        """
        Sends a JSON message to a specific user's active WebSocket connections.
        """
        if user_id in self.active_connections:
            broken_connections = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")
                    broken_connections.append(connection)
            if broken_connections:
                async with self._lock:
                    for connection in broken_connections:
                        if connection in self.active_connections[user_id]:
                            self.active_connections[user_id].remove(connection)

    async def broadcast(self, message: dict):
        """
        Broadcasts a message to all connected users.
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


# ============================================
# Notification Analytics Service
# ============================================
class NotificationAnalyticsService:
    """Provides notification analytics and statistics."""

    def __init__(self, db: Session):
        self.db = db

    def get_delivery_stats(self, user_id: Optional[int] = None):
        """
        Retrieves delivery statistics for notifications.
        """
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
        """
        Analyzes user engagement with notifications over a given period.
        """
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
        read_notifications = sum(1 for n in notifications if n.is_read)
        return {
            "total_notifications": total_notifications,
            "read_notifications": read_notifications,
            "engagement_rate": (
                (read_notifications / total_notifications * 100)
                if total_notifications > 0
                else 0
            ),
        }


# ============================================
# Notification Retry Handler
# ============================================
class NotificationRetryHandler:
    """Handles retrying of failed notifications."""

    def __init__(self, db: Session):
        self.db = db
        self.max_retries = 3
        self.retry_delays = [300, 600, 1800]  # 5 mins, 10 mins, 30 mins

    async def handle_failed_notification(self, notification_id: int):
        """
        Processes a failed notification for retry.
        """
        notification = get_model_by_id(self.db, models.Notification, notification_id)
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
        """
        Retries sending the notification after a specified delay.
        """
        await asyncio.sleep(delay)
        notification = get_model_by_id(self.db, models.Notification, notification_id)
        if not notification or notification.status != "retrying":
            return
        notification_service = NotificationService(self.db)
        success = await notification_service.deliver_notification(notification)
        notification.status = "delivered" if success else "failed"
        self.db.commit()


# ============================================
# Additional Handlers for Comments and Messages
# ============================================
class CommentNotificationHandler:
    """Handles notifications for comments."""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_comment(self, comment: models.Comment, post: models.Post):
        """
        Sends notifications when a new comment is added.
        """
        if comment.owner_id != post.owner_id:
            await self.notification_service.create_notification(
                user_id=post.owner_id,
                content=f"{comment.owner.username} commented on your post",
                notification_type="new_comment",
                priority=models.NotificationPriority.MEDIUM,
                category=models.NotificationCategory.SOCIAL,
                link=f"/post/{post.id}#comment-{comment.id}",
            )
        if comment.parent_id:
            parent_comment = get_model_by_id(self.db, models.Comment, comment.parent_id)
            if parent_comment and parent_comment.owner_id != comment.owner_id:
                await self.notification_service.create_notification(
                    user_id=parent_comment.owner_id,
                    content=f"{comment.owner.username} replied to your comment",
                    notification_type="comment_reply",
                    priority=models.NotificationPriority.MEDIUM,
                    category=models.NotificationCategory.SOCIAL,
                    link=f"/post/{post.id}#comment-{comment.id}",
                )


class MessageNotificationHandler:
    """Handles notifications for messages."""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_message(self, message: models.Message):
        """
        Sends a notification for a new message.
        """
        user_prefs = (
            self.db.query(models.NotificationPreferences)
            .filter(models.NotificationPreferences.user_id == message.receiver_id)
            .first()
        )
        if not user_prefs or user_prefs.message_notifications:
            await self.notification_service.create_notification(
                user_id=message.receiver_id,
                content=f"New message from {message.sender.username}",
                notification_type="new_message",
                priority=models.NotificationPriority.HIGH,
                category=models.NotificationCategory.SOCIAL,
                link=f"/messages/{message.sender_id}",
                metadata={
                    "sender_id": message.sender_id,
                    "sender_name": message.sender.username,
                    "message_type": message.message_type.value,
                    "conversation_id": message.conversation_id,
                },
            )


# ============================================
# Helper Functions
# ============================================
@handle_async_errors
async def send_real_time_notification(user_id: int, message: Union[str, dict]):
    """
    Sends a real-time notification to a user via WebSocket.
    """
    if isinstance(message, str):
        message = {"message": message, "type": "simple_notification"}
    await manager.send_personal_message(message, user_id)
    logger.info(f"Real-time notification sent to user {user_id}")


@handle_async_errors
async def send_mention_notification(to: str, mentioner: str, post_id: int):
    """
    Sends a mention notification via email.
    """
    subject = f"You've been mentioned by {mentioner}"
    body = f"""
    <div style="font-family: Arial, sans-serif;">
        <h2>New Mention</h2>
        <p>{mentioner} mentioned you in a post.</p>
        <a href="/post/{post_id}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px;">
            View Post
        </a>
    </div>
    """
    message = MessageSchema(subject=subject, recipients=[to], body=body, subtype="html")
    await send_email_notification(message)
    logger.info(f"Mention notification sent to {to}")


@handle_async_errors
async def send_login_notification(email: str, ip_address: str, user_agent: str):
    """
    Sends a login notification email with details of the login event.
    """
    subject = "New Login to Your Account"
    body = f"""
    <div style="font-family: Arial, sans-serif;">
        <h2>New Login Detected</h2>
        <p>New login detected with details:</p>
        <ul>
            <li><strong>IP Address:</strong> {ip_address}</li>
            <li><strong>Device:</strong> {user_agent}</li>
            <li><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
        </ul>
        <p>If this wasn't you, secure your account:</p>
        <ol>
            <li>Change password</li>
            <li>Enable 2FA</li>
            <li>Review activity</li>
        </ol>
        <a href="/security/account" style="display: inline-block; padding: 10px 20px; background-color: #dc3545; color: white; text-decoration: none; border-radius: 3px;">
            Secure Account
        </a>
    </div>
    """
    message = MessageSchema(
        subject=subject, recipients=[email], body=body, subtype="html"
    )
    await send_email_notification(message)
    logger.info(f"Login notification sent to {email}")


@handle_async_errors
async def deliver_scheduled_notification(
    notification_id: int, scheduled_time: datetime
):
    """
    Delivers a scheduled notification.
    """
    try:
        db = next(get_db())
        notification_service = NotificationService(db)
        notification = get_model_by_id(db, models.Notification, notification_id)
        if not notification:
            logger.error(f"Scheduled notification {notification_id} not found")
            return
        await notification_service.deliver_notification(notification)
        logger.info(f"Scheduled notification {notification_id} delivered")
    except Exception as e:
        logger.error(
            f"Error delivering scheduled notification {notification_id}: {str(e)}"
        )
        raise
    finally:
        db.close()


@handle_async_errors
async def send_bulk_notifications(
    user_ids: List[int],
    content: str,
    notification_type: str,
    db: Session,
    background_tasks: BackgroundTasks,
):
    """
    Sends bulk notifications to multiple users.
    """
    notification_service = NotificationService(db, background_tasks)
    tasks = []
    for user_id in user_ids:
        tasks.append(
            notification_service.create_notification(
                user_id=user_id,
                content=content,
                notification_type=notification_type,
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    logger.info(
        f"Bulk notifications: {success_count} successful out of {len(user_ids)}"
    )
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
):
    """
    Synchronously creates a notification.
    """
    try:
        new_notification = models.Notification(
            user_id=user_id,
            content=content,
            link=link,
            notification_type=notification_type,
            related_id=related_id,
        )
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)
        logger.info(f"Notification created for user {user_id}")
        return new_notification
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        db.rollback()
        raise


__all__ = [
    "manager",
    "NotificationService",
    "send_email_notification",
    "schedule_email_notification",
    "send_mention_notification",
    "send_login_notification",
    "send_bulk_notifications",
    "create_notification",
    "deliver_scheduled_notification",
    "NotificationBatcher",
    "NotificationDeliveryManager",
    "NotificationManager",
    "NotificationAnalyticsService",
    "NotificationRetryHandler",
    "CommentNotificationHandler",
    "MessageNotificationHandler",
    "send_real_time_notification",
]
