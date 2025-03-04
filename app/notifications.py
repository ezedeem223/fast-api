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

logger = logging.getLogger(__name__)

# Notification caches for performance
notification_cache = TTLCache(maxsize=1000, ttl=300)
delivery_status_cache = TTLCache(maxsize=5000, ttl=3600)
priority_notification_cache = TTLCache(maxsize=500, ttl=60)  # For urgent notifications


class NotificationBatcher:
    """Batch processor for notifications."""

    def __init__(self, max_batch_size: int = 100, max_wait_time: float = 1.0):
        self.batch = []
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self._lock = asyncio.Lock()
        self._last_flush = datetime.now(timezone.utc)

    async def add(self, notification: dict) -> None:
        async with self._lock:
            self.batch.append(notification)
            if (
                len(self.batch) >= self.max_batch_size
                or (datetime.now(timezone.utc) - self._last_flush).total_seconds()
                >= self.max_wait_time
            ):
                await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self.batch:
                return
            try:
                # Process the current batch
                await self._process_batch(self.batch)
            finally:
                self.batch = []
                self._last_flush = datetime.now(timezone.utc)

    async def _process_batch(self, notifications: List[dict]) -> None:
        # Group notifications by channel
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
        # Group messages by recipient email
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
            await fm.send_message(message)

    @staticmethod
    def _format_batch_email(notifications: List[dict]) -> str:
        return "\n".join(
            [
                f"<div><h3>{n['title']}</h3><p>{n['content']}</p></div>"
                for n in notifications
            ]
        )


class NotificationDeliveryManager:
    """Manages delivery of notifications with retry support."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 5  # Increase retry attempts
        self.retry_delays = [
            300,
            600,
            1200,
            2400,
            4800,
        ]  # Increasing delays (in seconds)
        self.error_tracking = {}
        self.batcher = NotificationBatcher()

    async def deliver_notification(self, notification: models.Notification) -> bool:
        """Deliver notification with retry and tracking."""
        try:
            delivery_key = f"delivery_{notification.id}"
            if delivery_key in delivery_status_cache:
                return delivery_status_cache[delivery_key]
            user_prefs = self._get_user_preferences(notification.user_id)
            # Prepare content based on user preferences
            content = await self._prepare_notification_content(notification, user_prefs)
            delivery_tasks = []
            if user_prefs.email_notifications:
                delivery_tasks.append(self._send_email(notification, content))
            if user_prefs.push_notifications:
                delivery_tasks.append(self._send_push(notification, content))
            if user_prefs.in_app_notifications:
                delivery_tasks.append(self._send_in_app(notification, content))
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

    async def _prepare_notification_content(
        self,
        notification: models.Notification,
        user_prefs: models.NotificationPreferences,
    ) -> str:
        """Prepare notification content with translation support."""
        content = notification.content
        if (
            user_prefs.auto_translate
            and user_prefs.preferred_language != notification.language
        ):
            content = await get_translated_content(
                content, user_prefs.preferred_language, notification.language
            )
        return content

    async def _update_delivery_status(
        self, notification: models.Notification, success: bool, results: List[Any]
    ) -> None:
        """Update notification delivery status."""
        status = (
            models.NotificationStatus.DELIVERED
            if success
            else models.NotificationStatus.FAILED
        )
        delivery_log = models.NotificationDeliveryLog(
            notification_id=notification.id,
            status=status.value,
            error_message=str(results) if not success else None,
            delivery_channel="all",
        )
        notification.status = status
        notification.delivery_status = {
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channels": self._format_delivery_results(results),
        }
        self.db.add(delivery_log)
        self.db.commit()

    def _format_delivery_results(self, results: List[Any]) -> Dict[str, Any]:
        """Format delivery results into a dict."""
        return {
            "email": (
                not isinstance(results[0], Exception) if len(results) > 0 else None
            ),
            "push": (
                not isinstance(results[1], Exception) if len(results) > 1 else None
            ),
            "in_app": (
                not isinstance(results[2], Exception) if len(results) > 2 else None
            ),
        }

    async def _handle_delivery_failure(
        self, notification: models.Notification, error: Exception
    ) -> None:
        """Handle failure in delivering notification."""
        if notification.retry_count >= self.max_retries:
            notification.status = models.NotificationStatus.FAILED
            notification.failure_reason = str(error)
            self.db.commit()
            return
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
        """Retry delivering a notification after a delay."""
        await asyncio.sleep(delay)
        notification = (
            self.db.query(models.Notification)
            .filter(models.Notification.id == notification_id)
            .first()
        )
        if (
            not notification
            or notification.status != models.NotificationStatus.RETRYING
        ):
            return
        await self.deliver_notification(notification)

    def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
        """Retrieve user notification preferences with caching."""
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

    async def _send_email(
        self, notification: models.Notification, content: str
    ) -> None:
        """Send notification via email."""
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
                subject="New Notification",
                recipients=[user.email],
                body=f"<div><h3>{notification.notification_type.replace('_', ' ').title()}</h3><p>{content}</p></div>",
                subtype="html",
            )
            await fm.send_message(message)
            logger.info(f"Email sent to {user.email}")
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            raise

    async def _send_push(self, notification: models.Notification, content: str) -> None:
        """Send push notification."""
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
            logger.error(f"Error sending push: {str(e)}")
            raise

    async def _send_in_app(
        self, notification: models.Notification, content: str
    ) -> None:
        """Send in-app notification via WebSocket."""
        try:
            message = {
                "type": "notification",
                "data": {
                    "id": notification.id,
                    "content": content,
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
            logger.error(f"Error sending in-app notification: {str(e)}")
            raise


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            logger.info(f"WebSocket connected for user {user_id}")

    async def disconnect(self, websocket: WebSocket, user_id: int):
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
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


class NotificationService:
    """Service to handle creation and delivery of notifications."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.max_retries = 3
        self.retry_delay = 300
        self.email_service = (
            EmailNotificationService()
        )  # Assuming these services are defined elsewhere
        self.push_service = PushNotificationService()
        self.websocket_manager = WebSocketManager()
        self.analytics_service = NotificationAnalyticsService()

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
        """Create a new notification with smart processing."""
        try:
            user_prefs = self._get_user_preferences(user_id)
            if not self._should_send_notification(user_prefs, category):
                logger.info(f"Notification skipped for user {user_id} per preferences")
                return None
            detected_lang = detect_language(content)
            if (
                user_prefs
                and user_prefs.auto_translate
                and user_prefs.preferred_language != detected_lang
            ):
                content = await get_translated_content(
                    content, user_prefs.preferred_language, detected_lang
                )
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

    async def handle_notification_failure(
        self, notification: models.Notification, error: Exception
    ):
        notification.status = models.NotificationStatus.FAILED
        notification.failure_reason = str(error)
        self.db.commit()
        if notification.retry_count < self.max_retries:
            await self.schedule_retry(notification)

    async def get_user_notification_stats(self, user_id: int) -> Dict[str, Any]:
        return await self.analytics_service.get_user_stats(user_id)

    async def bulk_create_notifications(
        self,
        notifications: List[schemas.NotificationCreate],
        batch_id: Optional[str] = None,
    ):
        batch_id = batch_id or str(uuid.uuid4())
        created_notifications = []
        for notification in notifications:
            notification.batch_id = batch_id
            created = await self.create_notification(**notification.dict())
            created_notifications.append(created)
        return created_notifications

    async def deliver_notification(self, notification: models.Notification):
        """Deliver notification with tracking of retries."""
        try:
            user_prefs = self._get_user_preferences(notification.user_id)
            delivery_tasks = []
            if user_prefs.email_notifications:
                delivery_tasks.append(self._send_email_notification(notification))
            if user_prefs.push_notifications:
                delivery_tasks.append(self._send_push_notification(notification))
            if user_prefs.in_app_notifications:
                delivery_tasks.append(self._send_realtime_notification(notification))
            results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            success = all(not isinstance(r, Exception) for r in results)
            status = (
                models.NotificationStatus.DELIVERED
                if success
                else models.NotificationStatus.FAILED
            )
            log = models.NotificationDeliveryLog(
                notification_id=notification.id,
                status=status.value,
                error_message=str(results) if not success else None,
                delivery_channel="all",
            )
            self.db.add(log)
            notification.status = status
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

    async def _send_realtime_notification(self, notification: models.Notification):
        """Send realtime notification via WebSocket."""
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

    async def retry_failed_notification(self, notification_id: int):
        """Retry sending a failed notification."""
        notification = (
            self.db.query(models.Notification)
            .filter(models.Notification.id == notification_id)
            .first()
        )
        if not notification or notification.retry_count >= self.max_retries:
            return False
        try:
            await self.deliver_notification(notification)
            notification.status = models.NotificationStatus.DELIVERED
            self.db.commit()
            return True
        except Exception as e:
            notification.retry_count += 1
            notification.last_retry = datetime.now(timezone.utc)
            notification.status = models.NotificationStatus.FAILED
            log = models.NotificationDeliveryLog(
                notification_id=notification.id,
                status="failed",
                error_message=str(e),
                delivery_channel="all",
            )
            self.db.add(log)
            self.db.commit()
            return False

    async def cleanup_old_notifications(self, days: int):
        """Archive notifications older than specified days."""
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        old_notifications = (
            self.db.query(models.Notification)
            .filter(
                models.Notification.created_at < threshold,
                models.Notification.is_read == True,
            )
            .all()
        )
        for notification in old_notifications:
            notification.is_archived = True
        self.db.commit()

    async def _send_email_notification(self, notification: models.Notification):
        """Send email notification."""
        try:
            user = (
                self.db.query(models.User)
                .filter(models.User.id == notification.user_id)
                .first()
            )
            if not user or not user.email:
                logger.warning(f"No email for user {notification.user_id}")
                return
            message = MessageSchema(
                subject=f"New {notification.notification_type.replace('_', ' ').title()}",
                recipients=[user.email],
                body=self._create_email_template(notification),
                subtype="html",
            )
            if self.background_tasks:
                self.background_tasks.add_task(fm.send_message, message)
            else:
                await fm.send_message(message)
            logger.info(f"Email sent to {user.email}")
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")

    async def _send_push_notification(self, notification: models.Notification):
        """Send push notification."""
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
                body=notification.content,
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

    def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
        """Get user notification preferences."""
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
        """Determine if notification should be sent based on preferences."""
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
        """Find an existing notification group or create a new one."""
        if not self._is_groupable_type(notification_type):
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

    def _create_email_template(self, notification: models.Notification) -> str:
        """Create an email template for the notification."""
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

    @staticmethod
    def _is_groupable_type(notification_type: str) -> bool:
        """Check if the notification type can be grouped."""
        groupable_types = {
            "post_like",
            "post_comment",
            "follower",
            "mention",
            "community_post",
            "message_received",
            "post_shared",
        }
        return notification_type in groupable_types

    def _schedule_delivery(self, notification: models.Notification):
        """Schedule the delivery of a notification."""
        if self.background_tasks:
            self.background_tasks.add_task(
                deliver_scheduled_notification,
                notification.id,
                notification.scheduled_for,
            )
            logger.info(
                f"Scheduled notification {notification.id} for {notification.scheduled_for}"
            )


class NotificationManager:
    """Central manager integrating notification components."""

    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_post_action(self, post_id: int, action_type: str, actor_id: int):
        """Handle notifications related to posts."""
        post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
        if not post:
            return
        notifications = []
        if action_type == "comment":
            notifications.append(
                {
                    "user_id": post.owner_id,
                    "content": "Someone commented on your post",
                    "type": "post_comment",
                    "link": f"/post/{post_id}",
                }
            )
        elif action_type == "new_post":
            followers = (
                self.db.query(models.Follow)
                .filter(models.Follow.followed_id == actor_id)
                .all()
            )
            for follower in followers:
                notifications.append(
                    {
                        "user_id": follower.follower_id,
                        "content": f"{post.owner.username} posted a new update",
                        "type": "new_post",
                        "link": f"/post/{post_id}",
                    }
                )
        for notification in notifications:
            await self.notification_service.create_notification(
                user_id=notification["user_id"],
                content=notification["content"],
                notification_type=notification["type"],
                link=notification["link"],
            )

    async def handle_message_action(self, message_id: int, action_type: str):
        """Handle notifications related to messages."""
        message = (
            self.db.query(models.Message)
            .filter(models.Message.id == message_id)
            .first()
        )
        if not message:
            return
        if action_type == "new_message":
            await self.notification_service.create_notification(
                user_id=message.receiver_id,
                content=f"You have a new message from {message.sender.username}",
                notification_type="new_message",
                link=f"/messages/{message.sender_id}",
            )

    async def handle_community_action(
        self, community_id: int, action_type: str, actor_id: int
    ):
        """Handle notifications related to communities."""
        community = (
            self.db.query(models.Community)
            .filter(models.Community.id == community_id)
            .first()
        )
        if not community:
            return
        if action_type == "new_post":
            members = (
                self.db.query(models.CommunityMember)
                .filter(models.CommunityMember.community_id == community_id)
                .all()
            )
            for member in members:
                if member.user_id != actor_id:
                    await self.notification_service.create_notification(
                        user_id=member.user_id,
                        content=f"New post in community {community.name}",
                        notification_type="community_post",
                        link=f"/community/{community_id}",
                    )


class NotificationAnalytics:
    """Notification analytics and statistics."""

    def __init__(self, db: Session):
        self.db = db

    def get_delivery_stats(self, user_id: Optional[int] = None):
        """Get delivery statistics for notifications."""
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
        """Analyze user engagement with notifications."""
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


class NotificationRetryHandler:
    """Handles retrying of failed notifications."""

    def __init__(self, db: Session):
        self.db = db
        self.max_retries = 3
        self.retry_delays = [300, 600, 1800]  # 5 mins, 10 mins, 30 mins

    async def handle_failed_notification(self, notification_id: int):
        """Process a failed notification for retry."""
        notification = (
            self.db.query(models.Notification)
            .filter(models.Notification.id == notification_id)
            .first()
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

    async def retry_notification(self, notification_id: int, delay: int):
        """Retry sending the notification after delay."""
        await asyncio.sleep(delay)
        notification = (
            self.db.query(models.Notification)
            .filter(models.Notification.id == notification_id)
            .first()
        )
        if not notification or notification.status != "retrying":
            return
        notification_service = NotificationService(self.db)
        success = await notification_service.deliver_notification(notification)
        notification.status = "delivered" if success else "failed"
        self.db.commit()


# Additional handlers for comments and messages (from file1)
class CommentNotificationHandler:
    """Handles notifications for comments."""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_comment(self, comment: models.Comment, post: models.Post):
        """Handle new comment notifications."""
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
            parent_comment = (
                self.db.query(models.Comment)
                .filter(models.Comment.id == comment.parent_id)
                .first()
            )
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
        """Handle new message notifications."""
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


# Helper functions
async def send_real_time_notification(user_id: int, message: Union[str, dict]):
    """Send a real-time notification."""
    try:
        if isinstance(message, str):
            message = {"message": message, "type": "simple_notification"}
        await manager.send_personal_message(message, user_id)
        logger.info(f"Real-time notification sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error in real-time notification to user {user_id}: {str(e)}")
        raise


async def send_mention_notification(to: str, mentioner: str, post_id: int):
    """Send a mention notification."""
    try:
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
        message = MessageSchema(
            subject=subject, recipients=[to], body=body, subtype="html"
        )
        await fm.send_message(message)
        logger.info(f"Mention notification sent to {to}")
    except Exception as e:
        logger.error(f"Error sending mention notification: {str(e)}")
        raise


async def send_login_notification(email: str, ip_address: str, user_agent: str):
    """Send a login notification."""
    try:
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
        await fm.send_message(message)
        logger.info(f"Login notification sent to {email}")
    except Exception as e:
        logger.error(f"Error sending login notification: {str(e)}")
        raise


async def deliver_scheduled_notification(
    notification_id: int, scheduled_time: datetime
):
    """Deliver a scheduled notification."""
    try:
        db = next(get_db())
        notification_service = NotificationService(db)
        notification = db.query(models.Notification).get(notification_id)
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


async def send_bulk_notifications(
    user_ids: List[int],
    content: str,
    notification_type: str,
    db: Session,
    background_tasks: BackgroundTasks,
):
    """Send bulk notifications to multiple users."""
    try:
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
    except Exception as e:
        logger.error(f"Error sending bulk notifications: {str(e)}")
        raise


def create_notification(
    db: Session,
    user_id: int,
    content: str,
    link: str,
    notification_type: str,
    related_id: Optional[int] = None,
):
    """Create a notification synchronously."""
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
    "send_real_time_notification",
    "send_mention_notification",
    "send_login_notification",
    "send_bulk_notifications",
    "create_notification",
    "deliver_scheduled_notification",
]
