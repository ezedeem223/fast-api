# في app/notifications.py

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

logger = logging.getLogger(__name__)

# كاش للإشعارات
notification_cache = TTLCache(maxsize=1000, ttl=300)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = []
            self.active_connections[user_id].append(websocket)
            logger.info(f"New WebSocket connection for user {user_id}")

    async def disconnect(self, websocket: WebSocket, user_id: int):
        async with self._lock:
            if user_id in self.active_connections:
                if websocket in self.active_connections[user_id]:
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
        """إرسال رسالة لجميع المستخدمين المتصلين"""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


class NotificationService:
    def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
        self.db = db
        self.background_tasks = background_tasks

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
        """إنشاء إشعار جديد مع المعالجة الذكية"""
        try:
            user_prefs = self._get_user_preferences(user_id)
            if not self._should_send_notification(user_prefs, category):
                logger.info(
                    f"Notification skipped for user {user_id} based on preferences"
                )
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

            logger.info(f"Notification created successfully for user {user_id}")
            return new_notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            self.db.rollback()
            raise

    async def deliver_notification(self, notification: models.Notification):
        """تسليم الإشعار عبر جميع القنوات المكونة"""
        try:
            user_prefs = self._get_user_preferences(notification.user_id)

            delivery_tasks = []

            if user_prefs.in_app_notifications:
                delivery_tasks.append(self._send_realtime_notification(notification))

            if user_prefs.email_notifications:
                delivery_tasks.append(self._send_email_notification(notification))

            if user_prefs.push_notifications:
                delivery_tasks.append(self._send_push_notification(notification))

            await asyncio.gather(*delivery_tasks)

            logger.info(f"Notification {notification.id} delivered successfully")

        except Exception as e:
            logger.error(f"Error delivering notification {notification.id}: {str(e)}")
            raise

    async def _send_realtime_notification(self, notification: models.Notification):
        """إرسال إشعار في الوقت الفعلي عبر WebSocket"""
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

    async def _send_email_notification(self, notification: models.Notification):
        """إرسال إشعار بالبريد الإلكتروني"""
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
                subject=f"New {notification.notification_type.replace('_', ' ').title()}",
                recipients=[user.email],
                body=self._create_email_template(notification),
                subtype="html",
            )

            if self.background_tasks:
                self.background_tasks.add_task(fm.send_message, message)
            else:
                await fm.send_message(message)

            logger.info(f"Email notification sent to {user.email}")

        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")

    async def _send_push_notification(self, notification: models.Notification):
        """إرسال إشعار Push"""
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
                logger.info(f"No active devices found for user {notification.user_id}")
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
                logger.info(
                    f"Push notification sent successfully to {response.success_count} devices"
                )

        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}")

    def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
        """الحصول على تفضيلات الإشعارات للمستخدم"""
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
        """التحقق من إمكانية إرسال الإشعار حسب التفضيلات"""
        if not prefs:
            return True

        # التحقق من ساعات الهدوء
        current_time = datetime.now().time()
        if (
            prefs.quiet_hours_start
            and prefs.quiet_hours_end
            and current_time >= prefs.quiet_hours_start
            and current_time <= prefs.quiet_hours_end
        ):
            return False

        # التحقق من تفضيلات الفئة
        category_enabled = prefs.categories_preferences.get(category.value, True)

        return category_enabled

    def _find_or_create_group(
        self, notification_type: str, user_id: int, related_id: Optional[int] = None
    ) -> Optional[models.NotificationGroup]:
        """البحث عن مجموعة مشابهة أو إنشاء واحدة جديدة"""
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
            logger.error(f"Error in notification grouping: {str(e)}")
            self.db.rollback()
            return None

    def _create_email_template(self, notification: models.Notification) -> str:
        """إنشاء قالب البريد الإلكتروني"""
        return f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    .notification-container {{ 
                        padding: 20px; 
                        background-color: #f5f5f5;
                        border-radius: 5px;
                        margin: 20px auto;
                        max-width: 600px;
                    }}
                    .notification-title {{
                        color: #333;
                        margin-bottom: 15px;
                    }}
                    .notification-content {{
                        color: #666;
                        margin-bottom: 20px;
                    }}
                    .notification-link {{
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #007bff;
                        color: white;
                        text-decoration: none;
                        border-radius: 3px;
                    }}
                    .notification-footer {{
                        margin-top: 20px;
                        font-size: 0.9em;
                        color: #999;
                    }}
                </style>
            </head>
            <body>
                <div class="notification-container">
                    <h2 class="notification-title">
                        {notification.notification_type.replace('_', ' ').title()}
                    </h2>
                    <div class="notification-content">
                        {notification.content}
                    </div>
                    {f'<a href="{notification.link}" class="notification-link">View Details</a>' if notification.link else ''}
                    <div class="notification-footer">
                        This notification was sent from {settings.SITE_NAME}
                    </div>
                </div>
            </body>
        </html>
        """

    @staticmethod
    def _is_groupable_type(notification_type: str) -> bool:
        """تحديد أنواع الإشعارات القابلة للتجميع"""
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
        """جدولة تسليم الإشعار"""
        if self.background_tasks:
            self.background_tasks.add_task(
                deliver_scheduled_notification,
                notification.id,
                notification.scheduled_for,
            )
            logger.info(
                f"Scheduled notification {notification.id} for delivery at {notification.scheduled_for}"
            )


# مواصلة الملف...


# دوال مساعدة للاستخدام المباشر
async def send_real_time_notification(user_id: int, message: Union[str, dict]):
    """إرسال إشعار في الوقت الفعلي"""
    try:
        if isinstance(message, str):
            message = {"message": message, "type": "simple_notification"}
        await manager.send_personal_message(message, user_id)
        logger.info(f"Realtime notification sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending realtime notification to user {user_id}: {str(e)}")
        raise


async def send_mention_notification(to: str, mentioner: str, post_id: int):
    """إرسال إشعار الإشارة"""
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
    """إرسال إشعار تسجيل الدخول"""
    try:
        subject = "New Login to Your Account"
        body = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>New Login Detected</h2>
            <p>We detected a new login to your account with the following details:</p>
            <ul>
                <li><strong>IP Address:</strong> {ip_address}</li>
                <li><strong>Device:</strong> {user_agent}</li>
                <li><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
            </ul>
            <p>If this wasn't you, please secure your account immediately by:</p>
            <ol>
                <li>Changing your password</li>
                <li>Enabling two-factor authentication</li>
                <li>Reviewing your recent activity</li>
            </ol>
            <a href="/security/account" style="display: inline-block; padding: 10px 20px; background-color: #dc3545; color: white; text-decoration: none; border-radius: 3px;">
                Secure Your Account
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
    """تسليم الإشعار المجدول"""
    try:
        db = next(get_db())
        notification_service = NotificationService(db)

        notification = db.query(models.Notification).get(notification_id)
        if not notification:
            logger.error(f"Scheduled notification {notification_id} not found")
            return

        await notification_service.deliver_notification(notification)
        logger.info(f"Scheduled notification {notification_id} delivered successfully")
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
    """إرسال إشعارات جماعية لمجموعة من المستخدمين"""
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
            f"Bulk notifications sent: {success_count} successful out of {len(user_ids)}"
        )

        return {
            "total": len(user_ids),
            "successful": success_count,
            "failed": len(user_ids) - success_count,
        }
    except Exception as e:
        logger.error(f"Error in bulk notification sending: {str(e)}")
        raise


def create_notification(
    db: Session,
    user_id: int,
    content: str,
    link: str,
    notification_type: str,
    related_id: Optional[int] = None,
):
    """إنشاء إشعار بشكل مباشر (غير متزامن)"""
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


# تصدير الدوال والكائنات المطلوبة
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
