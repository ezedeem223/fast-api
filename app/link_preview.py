import requests
from bs4 import BeautifulSoup
import validators


def extract_link_preview(url):
    if not validators.url(url):
        return None

    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")

        title = soup.title.string if soup.title else ""
        description = ""
        image = ""

        # محاولة استخراج الوصف
        meta_desc = soup.find("meta", attrs={"name": "description"})
        og_desc = soup.find("meta", property="og:description")
        if meta_desc:
            description = meta_desc["content"]
        elif og_desc:
            description = og_desc["content"]

        # محاولة استخراج الصورة
        og_image = soup.find("meta", property="og:image")
        if og_image:
            image = og_image["content"]

        return {"title": title, "description": description, "image": image, "url": url}
    except Exception as e:
        print(f"Error extracting link preview: {e}")
        return None


# لدي هذه المشروع اريد منك ان تقوم بمراجعته بشكل دقيق جدا جدا وتكون المراجعة شامله تشمل الملفات الرئيسية والفرعية وجميع الميزات ولاخاصيات وكل حرف وكلمه والمهمه الثانيه اعطني تقرير كامل بجميع الميزات والخاصيات والاشياء الموجوده به


# 1. عند تقديم ميزة جديدة لإضافتها للمشروع، قدّم لي إرشادات دقيقة حول كيفية دمجها بشكل صحيح مع جميع الملفات الرئيسية والفرعية.
# 2. تأكد من أن إضافة الميزة الجديدة لا تسبب أي تعارض أو أخطاء في بقية المزايا الموجودة في المشروع.
# 3. تحقق مما إذا كانت الميزة الجديدة موجودة بالفعل؛ إذا كانت كذلك، زودني باقتراحات لتحسينها أو دمجها بشكل أكثر كفاءة.
# 4. في كل مرة أطلب إضافة ميزة جديدة، تأكد من أن المشروع لا يزال يعمل بكفاءة وتوافق تام.
# 5. إذا كان هناك تحسين للميزة المقترحة، قدم لي هذا التحسين لتطبيقه.
# 6. بعد التأكد من نجاح إضافة الميزة، انتقل مباشرةً إلى الميزة التالية بناءً على التعليمات التي سأقدمها.
# مع الرجوع للملفات التي قدمتها:
# 7. عند تقديم الإرشادات والإضافات، اعتمد على الملفات التي قمت بتقديمها سابقًا لضمان التكامل بين الميزة الجديدة والمشروع الحالي.
# 8. إذا كانت الملفات السابقة تحتاج إلى تعديلات لتتناسب مع الميزة الجديدة، قدّم إرشادات محددة حول كيفية تعديلها أو تحديثها لتحقيق التكامل المطلوب.
# 9. التحقق ما اذا كانت الميزه موجوده بالفعل


# ترتيب الملفات: قم بترتيب الملفات بشكل صحيح، وأزل أي عناصر غير ضرورية. في حال كانت هناك مكونات ناقصة، أكملها بناءً على الهيكل الأساسي للمشروع.
# التحقق من التوافق: تحقق من أن جميع الملفات الرئيسية والفرعية متوافقة بشكل مثالي، مما يضمن أن الموقع يعمل بكفاءة ودون أخطاء.
# إضافة ميزات جديدة: عند تقديم ميزة جديدة، قدم لي إرشادات دقيقة ومفصلة حول كيفية دمجها بشكل صحيح مع جميع الملفات الأساسية والفرعية.
# ضمان عدم حدوث تعارض: تأكد من أن الميزة الجديدة لا تسبب أي تعارض أو أخطاء في المشروع بأكمله. إذا حدث ذلك، قدّم الحلول اللازمة لتجنب المشكلة.
# التحقق من الميزات الموجودة: قبل إضافة ميزة جديدة، تحقق مما إذا كانت موجودة بالفعل في المشروع. إذا كانت كذلك، زودني باقتراحات لتحسينها أو دمجها بشكل أكثر كفاءة.
# ضمان الأداء والكفاءة: في كل مرة أطلب فيها إضافة ميزة جديدة، تأكد من أن المشروع لا يزال يعمل بكفاءة وتوافق تام.
# تقديم تحسينات الميزات: إذا كان هناك تحسين للميزة المقترحة، قدّم لي هذا التحسين لتطبيقه وجعل المشروع أفضل.
# الاستمرارية في العمل: بعد التأكد من نجاح إضافة الميزة، انتقل مباشرةً إلى الميزة التالية بناءً على التعليمات التي سأقدمها.
# الاعتماد على الملفات السابقة: عند تقديم الإرشادات أو إضافة ميزات جديدة، اعتمد على الملفات التي قدمتها سابقًا لضمان التكامل بين الميزة الجديدة والمشروع الحالي.
# تعديل الملفات لتحقيق التكامل: إذا كانت الملفات السابقة تحتاج إلى تعديلات لتتناسب مع الميزة الجديدة، قدم إرشادات محددة حول كيفية تعديلها أو تحديثها لتحقيق التكامل المطلوب.
# التحقق المستمر لتفادي الأخطاء: تأكد من التحقق المستمر من الملفات المقدمة لتفادي أي أخطاء أو تعارضات، وضمان انسجام المشروع بشكل كامل


# خاصية اللغات تشمل جميع اللغات والمستخدم يختار ويتم تعين اللغة الافتراضيا ب اللغة العربية في الموقع والترجمه الفوري للبوستات والمقالات والكومنت والرسائل


# C:\Users\kglou\Desktop\fastapi\app\notifications.py:
# في app/notifications.py

# from fastapi import BackgroundTasks, WebSocket, HTTPException
# from fastapi_mail import MessageSchema
# from pydantic import EmailStr
# from typing import List, Union, Optional, Dict, Any
# from datetime import datetime, timezone, timedelta
# from sqlalchemy.orm import Session
# from sqlalchemy import and_, or_, func
# import json
# import logging
# from .database import get_db
# from . import models, schemas
# from .config import settings, fm
# from .firebase_config import send_multicast_notification
# from .utils import get_translated_content
# import asyncio
# from cachetools import TTLCache
# from .i18n import translate_text, detect_language
# from .models import (
#     Notification,
#     NotificationDeliveryLog,
#     NotificationGroup,
#     NotificationAnalytics,
#     NotificationStatus,
#     NotificationPriority,
#     NotificationCategory,
#     User,
#     NotificationPreferences,
# )

# logger = logging.getLogger(__name__)

# # كاش للإشعارات
# notification_cache = TTLCache(maxsize=1000, ttl=300)
# delivery_status_cache = TTLCache(maxsize=5000, ttl=3600)
# priority_notification_cache = TTLCache(maxsize=500, ttl=60)  # للإشعارات العاجلة


# class NotificationBatcher:
#     """معالج للإشعارات الجماعية"""

#     def __init__(self, max_batch_size: int = 100, max_wait_time: float = 1.0):
#         self.batch = []
#         self.max_batch_size = max_batch_size
#         self.max_wait_time = max_wait_time
#         self._lock = asyncio.Lock()
#         self._last_flush = datetime.now(timezone.utc)

#     async def add(self, notification: dict) -> None:
#         async with self._lock:
#             self.batch.append(notification)
#             if (
#                 len(self.batch) >= self.max_batch_size
#                 or (datetime.now(timezone.utc) - self._last_flush).total_seconds()
#                 >= self.max_wait_time
#             ):
#                 await self.flush()

#     async def flush(self) -> None:
#         async with self._lock:
#             if not self.batch:
#                 return
#             try:
#                 # معالجة الدفعة الحالية
#                 await self._process_batch(self.batch)
#             finally:
#                 self.batch = []
#                 self._last_flush = datetime.now(timezone.utc)

#     async def _process_batch(self, notifications: List[dict]) -> None:
#         # تجميع الإشعارات حسب نوع التسليم
#         email_notifications = []
#         push_notifications = []
#         in_app_notifications = []

#         for notif in notifications:
#             if notif.get("channel") == "email":
#                 email_notifications.append(notif)
#             elif notif.get("channel") == "push":
#                 push_notifications.append(notif)
#             else:
#                 in_app_notifications.append(notif)

#         # معالجة كل نوع على حدة
#         tasks = []
#         if email_notifications:
#             tasks.append(self._send_batch_emails(email_notifications))
#         if push_notifications:
#             tasks.append(self._send_batch_push(push_notifications))
#         if in_app_notifications:
#             tasks.append(self._send_batch_in_app(in_app_notifications))

#         await asyncio.gather(*tasks)

#     async def _send_batch_emails(self, notifications: List[dict]) -> None:
#         # تجميع الرسائل حسب المستلم
#         email_groups = {}
#         for notif in notifications:
#             email = notif["recipient"]
#             if email not in email_groups:
#                 email_groups[email] = []
#             email_groups[email].append(notif)

#         for email, notifs in email_groups.items():
#             message = MessageSchema(
#                 subject="New Notifications",
#                 recipients=[email],
#                 body=self._format_batch_email(notifs),
#                 subtype="html",
#             )
#             await fm.send_message(message)

#     @staticmethod
#     def _format_batch_email(notifications: List[dict]) -> str:
#         return "\n".join(
#             [
#                 f"<div><h3>{n['title']}</h3><p>{n['content']}</p></div>"
#                 for n in notifications
#             ]
#         )


# class NotificationDeliveryManager:
#     """مدير تسليم الإشعارات مع دعم متقدم للمحاولات المتكررة"""

#     def __init__(self, db, background_tasks: Optional[BackgroundTasks] = None):
#         self.db = db
#         self.background_tasks = background_tasks
#         self.max_retries = 5  # زيادة عدد المحاولات
#         self.retry_delays = [300, 600, 1200, 2400, 4800]  # تأخير متزايد
#         self.error_tracking = {}
#         self.batcher = NotificationBatcher()

#     async def deliver_notification(self, notification: models.Notification) -> bool:
#         """تسليم الإشعار مع دعم للمحاولات المتكررة والتتبع"""
#         try:
#             delivery_key = f"delivery_{notification.id}"
#             if delivery_key in delivery_status_cache:
#                 return delivery_status_cache[delivery_key]

#             user_prefs = self._get_user_preferences(notification.user_id)
#             # تحضير الإشعار حسب تفضيلات المستخدم
#             content = await self._prepare_notification_content(notification, user_prefs)

#             delivery_tasks = []
#             if user_prefs.email_notifications:
#                 delivery_tasks.append(self._send_email(notification, content))
#             if user_prefs.push_notifications:
#                 delivery_tasks.append(self._send_push(notification, content))
#             if user_prefs.in_app_notifications:
#                 delivery_tasks.append(self._send_in_app(notification, content))

#             results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
#             success = all(not isinstance(r, Exception) for r in results)

#             await self._update_delivery_statistics(notification, success, results)

#             delivery_status_cache[delivery_key] = success
#             return success

#         except Exception as e:
#             error_details = {
#                 "notification_id": notification.id,
#                 "error_type": type(e).__name__,
#                 "error_message": str(e),
#                 "timestamp": datetime.now(timezone.utc).isoformat(),
#             }
#             logger.error(f"Delivery error: {error_details}")
#             self.error_tracking[notification.id] = error_details

#             if notification.retry_count < self.max_retries:
#                 await self._schedule_retry(notification)
#             else:
#                 await self._handle_final_failure(notification, error_details)

#             return False

#     async def _prepare_notification_content(
#         self,
#         notification: models.Notification,
#         user_prefs: models.NotificationPreferences,
#     ) -> str:
#         """تحضير محتوى الإشعار مع دعم الترجمة"""
#         content = notification.content
#         if (
#             user_prefs.auto_translate
#             and user_prefs.preferred_language != notification.language
#         ):
#             content = await get_translated_content(
#                 content, user_prefs.preferred_language, notification.language
#             )
#         return content

#     async def _update_delivery_status(
#         self, notification: models.Notification, success: bool, results: List[Any]
#     ) -> None:
#         """تحديث حالة تسليم الإشعار"""
#         status = (
#             models.NotificationStatus.DELIVERED
#             if success
#             else models.NotificationStatus.FAILED
#         )

#         delivery_log = models.NotificationDeliveryLog(
#             notification_id=notification.id,
#             status=status.value,
#             error_message=str(results) if not success else None,
#             delivery_channel="all",
#         )

#         notification.status = status
#         notification.delivery_status = {
#             "success": success,
#             "timestamp": datetime.now(timezone.utc).isoformat(),
#             "channels": self._format_delivery_results(results),
#         }

#         self.db.add(delivery_log)
#         self.db.commit()

#     def _format_delivery_results(self, results: List[Any]) -> Dict[str, Any]:
#         """تنسيق نتائج التسليم"""
#         return {
#             "email": (
#                 not isinstance(results[0], Exception) if len(results) > 0 else None
#             ),
#             "push": not isinstance(results[1], Exception) if len(results) > 1 else None,
#             "in_app": (
#                 not isinstance(results[2], Exception) if len(results) > 2 else None
#             ),
#         }

#     async def _handle_delivery_failure(
#         self, notification: models.Notification, error: Exception
#     ) -> None:
#         """معالجة فشل تسليم الإشعار"""
#         if notification.retry_count >= self.max_retries:
#             notification.status = models.NotificationStatus.FAILED
#             notification.failure_reason = str(error)
#             self.db.commit()
#             return

#         retry_delay = self.retry_delays[notification.retry_count]
#         notification.retry_count += 1
#         notification.status = models.NotificationStatus.RETRYING
#         notification.next_retry = datetime.now(timezone.utc) + timedelta(
#             seconds=retry_delay
#         )

#         self.db.commit()

#         if self.background_tasks:
#             self.background_tasks.add_task(
#                 self.retry_delivery, notification.id, retry_delay
#             )

#     async def retry_delivery(self, notification_id: int, delay: int) -> None:
#         """إعادة محاولة تسليم الإشعار"""
#         await asyncio.sleep(delay)

#         notification = (
#             self.db.query(models.Notification)
#             .filter(models.Notification.id == notification_id)
#             .first()
#         )

#         if (
#             not notification
#             or notification.status != models.NotificationStatus.RETRYING
#         ):
#             return

#         await self.deliver_notification(notification)

#     def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
#         """الحصول على تفضيلات المستخدم مع التخزين المؤقت"""
#         cache_key = f"user_prefs_{user_id}"
#         if cache_key in notification_cache:
#             return notification_cache[cache_key]

#         prefs = (
#             self.db.query(models.NotificationPreferences)
#             .filter(models.NotificationPreferences.user_id == user_id)
#             .first()
#         )

#         if not prefs:
#             prefs = models.NotificationPreferences(user_id=user_id)
#             self.db.add(prefs)
#             self.db.commit()
#             self.db.refresh(prefs)

#         notification_cache[cache_key] = prefs
#         return prefs


# class ConnectionManager:
#     def __init__(self):
#         self.active_connections: Dict[int, List[WebSocket]] = {}
#         self._lock = asyncio.Lock()

#     async def connect(self, websocket: WebSocket, user_id: int):
#         await websocket.accept()
#         async with self._lock:
#             if user_id not in self.active_connections:
#                 self.active_connections[user_id] = []
#             self.active_connections[user_id].append(websocket)
#             logger.info(f"New WebSocket connection for user {user_id}")

#     async def disconnect(self, websocket: WebSocket, user_id: int):
#         async with self._lock:
#             if user_id in self.active_connections:
#                 if websocket in self.active_connections[user_id]:
#                     self.active_connections[user_id].remove(websocket)
#                 if not self.active_connections[user_id]:
#                     del self.active_connections[user_id]
#                 logger.info(f"WebSocket disconnected for user {user_id}")

#     async def send_personal_message(self, message: dict, user_id: int):
#         if user_id in self.active_connections:
#             broken_connections = []
#             for connection in self.active_connections[user_id]:
#                 try:
#                     await connection.send_json(message)
#                 except Exception as e:
#                     logger.error(f"Error sending message to user {user_id}: {str(e)}")
#                     broken_connections.append(connection)

#             if broken_connections:
#                 async with self._lock:
#                     for connection in broken_connections:
#                         if connection in self.active_connections[user_id]:
#                             self.active_connections[user_id].remove(connection)

#     async def broadcast(self, message: dict):
#         """إرسال رسالة لجميع المستخدمين المتصلين"""
#         for user_id in list(self.active_connections.keys()):
#             await self.send_personal_message(message, user_id)


# manager = ConnectionManager()


# class NotificationService:
#     def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
#         self.db = db
#         self.background_tasks = background_tasks
#         self.max_retries = 3
#         self.retry_delay = 300
#         self.email_service = EmailNotificationService()
#         self.push_service = PushNotificationService()
#         self.websocket_manager = WebSocketManager()
#         self.analytics_service = NotificationAnalyticsService()

#     async def create_notification(
#         self,
#         user_id: int,
#         content: str,
#         notification_type: str,
#         priority: models.NotificationPriority = models.NotificationPriority.MEDIUM,
#         category: models.NotificationCategory = models.NotificationCategory.SYSTEM,
#         link: Optional[str] = None,
#         related_id: Optional[int] = None,
#         metadata: Optional[dict] = None,
#         scheduled_for: Optional[datetime] = None,
#     ) -> Optional[models.Notification]:
#         """إنشاء إشعار جديد مع المعالجة الذكية"""
#         try:
#             user_prefs = self._get_user_preferences(user_id)
#             if not self._should_send_notification(user_prefs, category):
#                 logger.info(
#                     f"Notification skipped for user {user_id} based on preferences"
#                 )
#                 return None

#             detected_lang = detect_language(content)
#             if (
#                 user_prefs
#                 and user_prefs.auto_translate
#                 and user_prefs.preferred_language != detected_lang
#             ):
#                 content = await get_translated_content(
#                     content, user_prefs.preferred_language, detected_lang
#                 )

#             group = self._find_or_create_group(notification_type, user_id, related_id)

#             new_notification = models.Notification(
#                 user_id=user_id,
#                 content=content,
#                 notification_type=notification_type,
#                 priority=priority,
#                 category=category,
#                 link=link,
#                 related_id=related_id,
#                 metadata=metadata or {},
#                 scheduled_for=scheduled_for,
#                 group_id=group.id if group else None,
#                 language=detected_lang,
#             )

#             self.db.add(new_notification)
#             self.db.commit()
#             self.db.refresh(new_notification)

#             if scheduled_for and scheduled_for > datetime.now(timezone.utc):
#                 self._schedule_delivery(new_notification)
#             else:
#                 await self.deliver_notification(new_notification)

#             logger.info(f"Notification created successfully for user {user_id}")
#             return new_notification

#         except Exception as e:
#             logger.error(f"Error creating notification: {str(e)}")
#             self.db.rollback()
#             raise

#     async def handle_notification_failure(
#         self, notification: models.Notification, error: Exception
#     ):
#         notification.status = models.NotificationStatus.FAILED
#         notification.failure_reason = str(error)
#         self.db.commit()

#         if notification.retry_count < self.max_retries:
#             await self.schedule_retry(notification)

#     async def get_user_notification_stats(self, user_id: int) -> Dict[str, Any]:
#         return await self.analytics_service.get_user_stats(user_id)

#     async def bulk_create_notifications(
#         self,
#         notifications: List[schemas.NotificationCreate],
#         batch_id: Optional[str] = None,
#     ):
#         batch_id = batch_id or str(uuid.uuid4())
#         created_notifications = []

#         for notification in notifications:
#             notification.batch_id = batch_id
#             created = await self.create_notification(**notification.dict())
#             created_notifications.append(created)

#         return created_notifications

#     async def deliver_notification(self, notification: models.Notification):
#         """تحسين تسليم الإشعار مع تتبع محاولات التسليم"""
#         try:
#             user_prefs = self._get_user_preferences(notification.user_id)
#             delivery_tasks = []

#             if user_prefs.email_notifications:
#                 delivery_tasks.append(self._send_email_notification(notification))
#             if user_prefs.push_notifications:
#                 delivery_tasks.append(self._send_push_notification(notification))
#             if user_prefs.in_app_notifications:
#                 delivery_tasks.append(self._send_realtime_notification(notification))

#             results = await asyncio.gather(*delivery_tasks, return_exceptions=True)

#             success = all(not isinstance(r, Exception) for r in results)
#             status = (
#                 models.NotificationStatus.DELIVERED
#                 if success
#                 else models.NotificationStatus.FAILED
#             )

#             log = models.NotificationDeliveryLog(
#                 notification_id=notification.id,
#                 status=status.value,
#                 error_message=str(results) if not success else None,
#                 delivery_channel="all",
#             )
#             self.db.add(log)
#             notification.status = status
#             self.db.commit()

#         except Exception as e:
#             notification.status = models.NotificationStatus.FAILED
#             log = models.NotificationDeliveryLog(
#                 notification_id=notification.id,
#                 status="failed",
#                 error_message=str(e),
#                 delivery_channel="all",
#             )
#             self.db.add(log)
#             self.db.commit()
#             raise

#     async def _send_realtime_notification(self, notification: models.Notification):
#         """إرسال إشعار في الوقت الفعلي عبر WebSocket"""
#         try:
#             message = {
#                 "type": "notification",
#                 "data": {
#                     "id": notification.id,
#                     "content": notification.content,
#                     "notification_type": notification.notification_type,
#                     "priority": notification.priority.value,
#                     "category": notification.category.value,
#                     "link": notification.link,
#                     "created_at": notification.created_at.isoformat(),
#                     "metadata": notification.metadata,
#                 },
#             }
#             await manager.send_personal_message(message, notification.user_id)
#         except Exception as e:
#             logger.error(f"Error sending realtime notification: {str(e)}")

#     async def retry_failed_notification(self, notification_id: int):
#         """إعادة محاولة إرسال الإشعارات الفاشلة"""
#         notification = (
#             self.db.query(models.Notification)
#             .filter(models.Notification.id == notification_id)
#             .first()
#         )

#         if not notification or notification.retry_count >= self.max_retries:
#             return False

#         try:
#             await self.deliver_notification(notification)
#             notification.status = models.NotificationStatus.DELIVERED
#             self.db.commit()
#             return True
#         except Exception as e:
#             notification.retry_count += 1
#             notification.last_retry = datetime.now(timezone.utc)
#             notification.status = models.NotificationStatus.FAILED

#             log = models.NotificationDeliveryLog(
#                 notification_id=notification.id,
#                 status="failed",
#                 error_message=str(e),
#                 delivery_channel="all",
#             )
#             self.db.add(log)
#             self.db.commit()
#             return False

#     async def cleanup_old_notifications(self, days: int):
#         """تنظيف الإشعارات القديمة"""
#         threshold = datetime.now(timezone.utc) - timedelta(days=days)
#         old_notifications = (
#             self.db.query(models.Notification)
#             .filter(
#                 models.Notification.created_at < threshold,
#                 models.Notification.is_read == True,
#             )
#             .all()
#         )

#         for notification in old_notifications:
#             notification.is_archived = True
#         self.db.commit()

#     async def _send_email_notification(self, notification: models.Notification):
#         """إرسال إشعار بالبريد الإلكتروني"""
#         try:
#             user = (
#                 self.db.query(models.User)
#                 .filter(models.User.id == notification.user_id)
#                 .first()
#             )
#             if not user or not user.email:
#                 logger.warning(f"No email found for user {notification.user_id}")
#                 return

#             message = MessageSchema(
#                 subject=f"New {notification.notification_type.replace('_', ' ').title()}",
#                 recipients=[user.email],
#                 body=self._create_email_template(notification),
#                 subtype="html",
#             )

#             if self.background_tasks:
#                 self.background_tasks.add_task(fm.send_message, message)
#             else:
#                 await fm.send_message(message)

#             logger.info(f"Email notification sent to {user.email}")

#         except Exception as e:
#             logger.error(f"Error sending email notification: {str(e)}")

#     async def _send_push_notification(self, notification: models.Notification):
#         """إرسال إشعار Push"""
#         try:
#             user_devices = (
#                 self.db.query(models.UserDevice)
#                 .filter(
#                     models.UserDevice.user_id == notification.user_id,
#                     models.UserDevice.is_active == True,
#                 )
#                 .all()
#             )

#             if not user_devices:
#                 logger.info(f"No active devices found for user {notification.user_id}")
#                 return

#             tokens = [device.fcm_token for device in user_devices]

#             response = send_multicast_notification(
#                 tokens=tokens,
#                 title=notification.notification_type.replace("_", " ").title(),
#                 body=notification.content,
#                 data={
#                     "notification_id": str(notification.id),
#                     "type": notification.notification_type,
#                     "link": notification.link or "",
#                     "priority": notification.priority.value,
#                     "category": notification.category.value,
#                 },
#             )

#             if response and hasattr(response, "success_count"):
#                 logger.info(
#                     f"Push notification sent successfully to {response.success_count} devices"
#                 )

#         except Exception as e:
#             logger.error(f"Error sending push notification: {str(e)}")

#     def _get_user_preferences(self, user_id: int) -> models.NotificationPreferences:
#         """الحصول على تفضيلات الإشعارات للمستخدم"""
#         prefs = (
#             self.db.query(models.NotificationPreferences)
#             .filter(models.NotificationPreferences.user_id == user_id)
#             .first()
#         )

#         if not prefs:
#             prefs = models.NotificationPreferences(user_id=user_id)
#             self.db.add(prefs)
#             self.db.commit()
#             self.db.refresh(prefs)

#         return prefs

#     def _should_send_notification(
#         self,
#         prefs: models.NotificationPreferences,
#         category: models.NotificationCategory,
#     ) -> bool:
#         """التحقق من إمكانية إرسال الإشعار حسب التفضيلات"""
#         if not prefs:
#             return True

#         # التحقق من ساعات الهدوء
#         current_time = datetime.now().time()
#         if (
#             prefs.quiet_hours_start
#             and prefs.quiet_hours_end
#             and current_time >= prefs.quiet_hours_start
#             and current_time <= prefs.quiet_hours_end
#         ):
#             return False

#         # التحقق من تفضيلات الفئة
#         category_enabled = prefs.categories_preferences.get(category.value, True)

#         return category_enabled

#     def _find_or_create_group(
#         self, notification_type: str, user_id: int, related_id: Optional[int] = None
#     ) -> Optional[models.NotificationGroup]:
#         """البحث عن مجموعة مشابهة أو إنشاء واحدة جديدة"""
#         if not self._is_groupable_type(notification_type):
#             return None

#         try:
#             existing_group = (
#                 self.db.query(models.NotificationGroup)
#                 .join(models.Notification)
#                 .filter(
#                     and_(
#                         models.NotificationGroup.group_type == notification_type,
#                         models.Notification.user_id == user_id,
#                         models.Notification.created_at
#                         >= datetime.now(timezone.utc) - timedelta(hours=24),
#                     )
#                 )
#                 .first()
#             )

#             if existing_group:
#                 existing_group.count += 1
#                 existing_group.last_updated = datetime.now(timezone.utc)
#                 self.db.commit()
#                 return existing_group

#             new_group = models.NotificationGroup(group_type=notification_type)
#             self.db.add(new_group)
#             self.db.commit()
#             self.db.refresh(new_group)
#             return new_group

#         except Exception as e:
#             logger.error(f"Error in notification grouping: {str(e)}")
#             self.db.rollback()
#             return None

#     def _create_email_template(self, notification: models.Notification) -> str:
#         """إنشاء قالب البريد الإلكتروني"""
#         return f"""
#         <html>
#             <head>
#                 <style>
#                     body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
#                     .notification-container {{
#                         padding: 20px;
#                         background-color: #f5f5f5;
#                         border-radius: 5px;
#                         margin: 20px auto;
#                         max-width: 600px;
#                     }}
#                     .notification-title {{
#                         color: #333;
#                         margin-bottom: 15px;
#                     }}
#                     .notification-content {{
#                         color: #666;
#                         margin-bottom: 20px;
#                     }}
#                     .notification-link {{
#                         display: inline-block;
#                         padding: 10px 20px;
#                         background-color: #007bff;
#                         color: white;
#                         text-decoration: none;
#                         border-radius: 3px;
#                     }}
#                     .notification-footer {{
#                         margin-top: 20px;
#                         font-size: 0.9em;
#                         color: #999;
#                     }}
#                 </style>
#             </head>
#             <body>
#                 <div class="notification-container">
#                     <h2 class="notification-title">
#                         {notification.notification_type.replace('_', ' ').title()}
#                     </h2>
#                     <div class="notification-content">
#                         {notification.content}
#                     </div>
#                     {f'<a href="{notification.link}" class="notification-link">View Details</a>' if notification.link else ''}
#                     <div class="notification-footer">
#                         This notification was sent from {settings.SITE_NAME}
#                     </div>
#                 </div>
#             </body>
#         </html>
#         """

#     @staticmethod
#     def _is_groupable_type(notification_type: str) -> bool:
#         """تحديد أنواع الإشعارات القابلة للتجميع"""
#         groupable_types = {
#             "post_like",
#             "post_comment",
#             "follower",
#             "mention",
#             "community_post",
#             "message_received",
#             "post_shared",
#         }
#         return notification_type in groupable_types

#     def _schedule_delivery(self, notification: models.Notification):
#         """جدولة تسليم الإشعار"""
#         if self.background_tasks:
#             self.background_tasks.add_task(
#                 deliver_scheduled_notification,
#                 notification.id,
#                 notification.scheduled_for,
#             )
#             logger.info(
#                 f"Scheduled notification {notification.id} for delivery at {notification.scheduled_for}"
#             )


# # مواصلة الملف...


# # دوال مساعدة للاستخدام المباشر
# async def send_real_time_notification(user_id: int, message: Union[str, dict]):
#     """إرسال إشعار في الوقت الفعلي"""
#     try:
#         if isinstance(message, str):
#             message = {"message": message, "type": "simple_notification"}
#         await manager.send_personal_message(message, user_id)
#         logger.info(f"Realtime notification sent to user {user_id}")
#     except Exception as e:
#         logger.error(f"Error sending realtime notification to user {user_id}: {str(e)}")
#         raise


# async def send_mention_notification(to: str, mentioner: str, post_id: int):
#     """إرسال إشعار الإشارة"""
#     try:
#         subject = f"You've been mentioned by {mentioner}"
#         body = f"""
#         <div style="font-family: Arial, sans-serif;">
#             <h2>New Mention</h2>
#             <p>{mentioner} mentioned you in a post.</p>
#             <a href="/post/{post_id}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px;">
#                 View Post
#             </a>
#         </div>
#         """
#         message = MessageSchema(
#             subject=subject, recipients=[to], body=body, subtype="html"
#         )
#         await fm.send_message(message)
#         logger.info(f"Mention notification sent to {to}")
#     except Exception as e:
#         logger.error(f"Error sending mention notification: {str(e)}")
#         raise


# async def send_login_notification(email: str, ip_address: str, user_agent: str):
#     """إرسال إشعار تسجيل الدخول"""
#     try:
#         subject = "New Login to Your Account"
#         body = f"""
#         <div style="font-family: Arial, sans-serif;">
#             <h2>New Login Detected</h2>
#             <p>We detected a new login to your account with the following details:</p>
#             <ul>
#                 <li><strong>IP Address:</strong> {ip_address}</li>
#                 <li><strong>Device:</strong> {user_agent}</li>
#                 <li><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
#             </ul>
#             <p>If this wasn't you, please secure your account immediately by:</p>
#             <ol>
#                 <li>Changing your password</li>
#                 <li>Enabling two-factor authentication</li>
#                 <li>Reviewing your recent activity</li>
#             </ol>
#             <a href="/security/account" style="display: inline-block; padding: 10px 20px; background-color: #dc3545; color: white; text-decoration: none; border-radius: 3px;">
#                 Secure Your Account
#             </a>
#         </div>
#         """
#         message = MessageSchema(
#             subject=subject, recipients=[email], body=body, subtype="html"
#         )
#         await fm.send_message(message)
#         logger.info(f"Login notification sent to {email}")
#     except Exception as e:
#         logger.error(f"Error sending login notification: {str(e)}")
#         raise


# async def deliver_scheduled_notification(
#     notification_id: int, scheduled_time: datetime
# ):
#     """تسليم الإشعار المجدول"""
#     try:
#         db = next(get_db())
#         notification_service = NotificationService(db)

#         notification = db.query(models.Notification).get(notification_id)
#         if not notification:
#             logger.error(f"Scheduled notification {notification_id} not found")
#             return

#         await notification_service.deliver_notification(notification)
#         logger.info(f"Scheduled notification {notification_id} delivered successfully")
#     except Exception as e:
#         logger.error(
#             f"Error delivering scheduled notification {notification_id}: {str(e)}"
#         )
#         raise
#     finally:
#         db.close()


# async def send_bulk_notifications(
#     user_ids: List[int],
#     content: str,
#     notification_type: str,
#     db: Session,
#     background_tasks: BackgroundTasks,
# ):
#     """إرسال إشعارات جماعية لمجموعة من المستخدمين"""
#     try:
#         notification_service = NotificationService(db, background_tasks)
#         tasks = []

#         for user_id in user_ids:
#             tasks.append(
#                 notification_service.create_notification(
#                     user_id=user_id,
#                     content=content,
#                     notification_type=notification_type,
#                 )
#             )

#         results = await asyncio.gather(*tasks, return_exceptions=True)

#         success_count = sum(1 for r in results if not isinstance(r, Exception))
#         logger.info(
#             f"Bulk notifications sent: {success_count} successful out of {len(user_ids)}"
#         )

#         return {
#             "total": len(user_ids),
#             "successful": success_count,
#             "failed": len(user_ids) - success_count,
#         }
#     except Exception as e:
#         logger.error(f"Error in bulk notification sending: {str(e)}")
#         raise


# def create_notification(
#     db: Session,
#     user_id: int,
#     content: str,
#     link: str,
#     notification_type: str,
#     related_id: Optional[int] = None,
# ):
#     """إنشاء إشعار بشكل مباشر (غير متزامن)"""
#     try:
#         new_notification = models.Notification(
#             user_id=user_id,
#             content=content,
#             link=link,
#             notification_type=notification_type,
#             related_id=related_id,
#         )
#         db.add(new_notification)
#         db.commit()
#         db.refresh(new_notification)
#         logger.info(f"Notification created for user {user_id}")
#         return new_notification
#     except Exception as e:
#         logger.error(f"Error creating notification: {str(e)}")
#         db.rollback()
#         raise


# # تصدير الدوال والكائنات المطلوبة
# __all__ = [
#     "manager",
#     "NotificationService",
#     "send_real_time_notification",
#     "send_mention_notification",
#     "send_login_notification",
#     "send_bulk_notifications",
#     "create_notification",
#     "deliver_scheduled_notification",
# ]


# class NotificationManager:
#     """مدير مركزي للإشعارات يتكامل مع جميع وحدات النظام"""

#     def __init__(self, db: Session, background_tasks: Optional[BackgroundTasks] = None):
#         self.db = db
#         self.background_tasks = background_tasks
#         self.notification_service = NotificationService(db, background_tasks)

#     async def handle_post_action(self, post_id: int, action_type: str, actor_id: int):
#         """معالجة الإشعارات المتعلقة بالمنشورات"""
#         post = self.db.query(models.Post).filter(models.Post.id == post_id).first()
#         if not post:
#             return

#         notifications = []

#         # إشعار صاحب المنشور
#         if action_type == "comment":
#             notifications.append(
#                 {
#                     "user_id": post.owner_id,
#                     "content": f"علق شخص ما على منشورك",
#                     "type": "post_comment",
#                     "link": f"/post/{post_id}",
#                 }
#             )

#         # إشعار المتابعين
#         elif action_type == "new_post":
#             followers = (
#                 self.db.query(models.Follow)
#                 .filter(models.Follow.followed_id == actor_id)
#                 .all()
#             )

#             for follower in followers:
#                 notifications.append(
#                     {
#                         "user_id": follower.follower_id,
#                         "content": f"قام {post.owner.username} بنشر منشور جديد",
#                         "type": "new_post",
#                         "link": f"/post/{post_id}",
#                     }
#                 )

#         # إرسال الإشعارات
#         for notification in notifications:
#             await self.notification_service.create_notification(
#                 user_id=notification["user_id"],
#                 content=notification["content"],
#                 notification_type=notification["type"],
#                 link=notification["link"],
#             )

#     async def handle_message_action(self, message_id: int, action_type: str):
#         """معالجة الإشعارات المتعلقة بالرسائل"""
#         message = (
#             self.db.query(models.Message)
#             .filter(models.Message.id == message_id)
#             .first()
#         )
#         if not message:
#             return

#         if action_type == "new_message":
#             await self.notification_service.create_notification(
#                 user_id=message.receiver_id,
#                 content=f"لديك رسالة جديدة من {message.sender.username}",
#                 notification_type="new_message",
#                 link=f"/messages/{message.sender_id}",
#             )

#     async def handle_community_action(
#         self, community_id: int, action_type: str, actor_id: int
#     ):
#         """معالجة الإشعارات المتعلقة بالمجتمعات"""
#         community = (
#             self.db.query(models.Community)
#             .filter(models.Community.id == community_id)
#             .first()
#         )
#         if not community:
#             return

#         if action_type == "new_post":
#             members = (
#                 self.db.query(models.CommunityMember)
#                 .filter(models.CommunityMember.community_id == community_id)
#                 .all()
#             )

#             for member in members:
#                 if member.user_id != actor_id:
#                     await self.notification_service.create_notification(
#                         user_id=member.user_id,
#                         content=f"منشور جديد في مجتمع {community.name}",
#                         notification_type="community_post",
#                         link=f"/community/{community_id}",
#                     )


# # 2. تحسين آلية التتبع والتحليل
# class NotificationAnalytics:
#     """تحليلات وإحصائيات الإشعارات"""

#     def __init__(self, db: Session):
#         self.db = db

#     def get_delivery_stats(self, user_id: Optional[int] = None):
#         """الحصول على إحصائيات تسليم الإشعارات"""
#         query = self.db.query(models.NotificationDeliveryLog)

#         if user_id:
#             query = query.join(models.Notification).filter(
#                 models.Notification.user_id == user_id
#             )

#         total = query.count()
#         successful = query.filter(
#             models.NotificationDeliveryLog.status == "delivered"
#         ).count()
#         failed = query.filter(models.NotificationDeliveryLog.status == "failed").count()

#         return {
#             "total": total,
#             "successful": successful,
#             "failed": failed,
#             "success_rate": (successful / total * 100) if total > 0 else 0,
#         }

#     def get_user_engagement(self, user_id: int, days: int = 30):
#         """تحليل تفاعل المستخدم مع الإشعارات"""
#         cutoff_date = datetime.now() - timedelta(days=days)

#         notifications = (
#             self.db.query(models.Notification)
#             .filter(
#                 models.Notification.user_id == user_id,
#                 models.Notification.created_at >= cutoff_date,
#             )
#             .all()
#         )

#         total_notifications = len(notifications)
#         read_notifications = sum(1 for n in notifications if n.is_read)

#         return {
#             "total_notifications": total_notifications,
#             "read_notifications": read_notifications,
#             "engagement_rate": (
#                 (read_notifications / total_notifications * 100)
#                 if total_notifications > 0
#                 else 0
#             ),
#         }


# # 3. تحسين معالجة الأخطاء وإعادة المحاولة
# class NotificationRetryHandler:
#     """معالج إعادة محاولة إرسال الإشعارات الفاشلة"""

#     def __init__(self, db: Session):
#         self.db = db
#         self.max_retries = 3
#         self.retry_delays = [300, 600, 1800]  # 5 mins, 10 mins, 30 mins

#     async def handle_failed_notification(self, notification_id: int):
#         """معالجة الإشعارات الفاشلة"""
#         notification = (
#             self.db.query(models.Notification)
#             .filter(models.Notification.id == notification_id)
#             .first()
#         )
#         if not notification:
#             return

#         if notification.retry_count >= self.max_retries:
#             notification.status = "permanently_failed"
#             self.db.commit()
#             return

#         delay = self.retry_delays[notification.retry_count]
#         notification.retry_count += 1
#         notification.status = "retrying"
#         notification.next_retry = datetime.now() + timedelta(seconds=delay)

#         self.db.commit()

#         # جدولة إعادة المحاولة
#         background_tasks.add_task(self.retry_notification, notification_id, delay)

#     async def retry_notification(self, notification_id: int, delay: int):
#         """إعادة محاولة إرسال الإشعار"""
#         await asyncio.sleep(delay)

#         notification = (
#             self.db.query(models.Notification)
#             .filter(models.Notification.id == notification_id)
#             .first()
#         )
#         if not notification or notification.status != "retrying":
#             return

#         notification_service = NotificationService(self.db)
#         success = await notification_service.deliver_notification(notification)

#         if success:
#             notification.status = "delivered"
#         else:
#             await self.handle_failed_notification(notification_id)

#         self.db.commit()
