from celery import Celery
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
from app.config import settings
from app.database import SessionLocal
from app import models
from datetime import datetime, timedelta
from .routers.post import send_notifications_and_share
from app.utils import is_content_offensive
from celery.schedules import crontab
from sqlalchemy.orm import Session
import firebase_admin
from firebase_admin import credentials, messaging
from . import models

# إعداد Celery
celery_app = Celery(
    "worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
)

# إعدادات البريد الإلكتروني
conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_FROM_NAME="YourAppName Notifications",
    MAIL_TLS=True,
    MAIL_SSL=False,
    USE_CREDENTIALS=True,
)

# إنشاء كائن FastMail مرة واحدة لاستخدامه في جميع المهام
fm = FastMail(conf)
celery_app.conf.beat_schedule["check-old-posts-content"] = {
    "task": "app.celery_worker.check_old_posts_content",
    "schedule": crontab(hour=3, minute=0),  # تشغيل كل يوم في الساعة 3 صباحًا
}


celery_app.conf.beat_schedule.update(
    {
        "cleanup-old-notifications": {
            "task": "app.celery_worker.cleanup_old_notifications",
            "schedule": crontab(hour=0, minute=0),  # تشغيل يومياً في منتصف الليل
        },
        "process-scheduled-notifications": {
            "task": "app.celery_worker.process_scheduled_notifications",
            "schedule": 60.0,  # تشغيل كل دقيقة
        },
        "update-notification-analytics": {
            "task": "app.celery_worker.update_notification_analytics",
            "schedule": crontab(hour="*/1"),  # تشغيل كل ساعة
        },
    }
)


@celery_app.task
def cleanup_old_notifications():
    """تنظيف الإشعارات القديمة وتحديث الإحصائيات"""
    db = SessionLocal()
    try:
        # أرشفة الإشعارات القديمة المقروءة
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        db.query(models.Notification).filter(
            models.Notification.is_read == True,
            models.Notification.created_at < thirty_days_ago,
            models.Notification.is_archived == False,
        ).update({"is_archived": True})

        # حذف الإشعارات القديمة جداً
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        db.query(models.Notification).filter(
            models.Notification.created_at < ninety_days_ago,
            models.Notification.is_archived == True,
        ).update({"is_deleted": True})

        db.commit()
    finally:
        db.close()


@celery_app.task
def process_scheduled_notifications():
    """معالجة الإشعارات المجدولة"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        scheduled_notifications = (
            db.query(models.Notification)
            .filter(
                models.Notification.scheduled_for <= now,
                models.Notification.is_delivered == False,
            )
            .all()
        )

        for notification in scheduled_notifications:
            deliver_notification.delay(notification.id)
            notification.is_delivered = True

        db.commit()
    finally:
        db.close()


@celery_app.task
def deliver_notification(notification_id: int):
    """تسليم الإشعار عبر جميع القنوات المكونة"""
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).get(notification_id)
        if not notification:
            return

        user_prefs = (
            db.query(models.NotificationPreferences)
            .filter(models.NotificationPreferences.user_id == notification.user_id)
            .first()
        )

        if not user_prefs:
            return

        # إرسال إشعار البريد الإلكتروني
        if user_prefs.email_notifications:
            send_email_notification.delay(notification_id)

        # إرسال إشعار Push
        if user_prefs.push_notifications:
            send_push_notification.delay(notification_id)

    finally:
        db.close()


@celery_app.task
def send_push_notification(notification_id: int):
    """إرسال إشعار Push باستخدام Firebase"""
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).get(notification_id)
        if not notification:
            return

        devices = (
            db.query(models.UserDevice)
            .filter(
                models.UserDevice.user_id == notification.user_id,
                models.UserDevice.is_active == True,
            )
            .all()
        )

        for device in devices:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="New Notification", body=notification.content
                ),
                data={
                    "notification_id": str(notification.id),
                    "type": notification.notification_type,
                    "link": notification.link or "",
                },
                token=device.fcm_token,
            )
            messaging.send(message)

    except Exception as e:
        print(f"Error sending push notification: {str(e)}")
    finally:
        db.close()


@celery_app.task
def update_notification_analytics():
    """تحديث تحليلات الإشعارات"""
    db = SessionLocal()
    try:
        users = db.query(models.User).all()
        for user in users:
            analytics = calculate_user_notification_analytics(db, user.id)

            user_analytics = (
                db.query(models.NotificationAnalytics)
                .filter(models.NotificationAnalytics.user_id == user.id)
                .first()
            )

            if not user_analytics:
                user_analytics = models.NotificationAnalytics(user_id=user.id)
                db.add(user_analytics)

            user_analytics.engagement_rate = analytics["engagement_rate"]
            user_analytics.response_time = analytics["response_time"]
            user_analytics.peak_hours = analytics["peak_hours"]
            user_analytics.updated_at = datetime.utcnow()

        db.commit()
    finally:
        db.close()


@celery_app.task
def send_email_task(email_to: List[EmailStr], subject: str, body: str):
    """
    مهمة لإرسال البريد الإلكتروني باستخدام Celery.
    """
    try:
        message = MessageSchema(
            subject=subject,
            recipients=email_to,
            body=body,
            subtype="html",
        )
        fm.send_message(message)
    except Exception as e:
        print(f"Failed to send email: {e}")


@celery_app.task
def check_old_posts_content():
    db = SessionLocal()
    try:
        old_posts = db.query(models.Post).filter(models.Post.is_flagged == False).all()
        for post in old_posts:
            is_offensive, confidence = is_content_offensive(post.content)
            if is_offensive:
                post.is_flagged = True
                post.flag_reason = f"AI detected potentially offensive content (delayed check, confidence: {confidence:.2f})"
        db.commit()
    finally:
        db.close()


@celery_app.task
def unblock_user(blocker_id: int, blocked_id: int):
    db = SessionLocal()
    try:
        block = (
            db.query(models.Block)
            .filter(
                models.Block.blocker_id == blocker_id,
                models.Block.blocked_id == blocked_id,
            )
            .first()
        )
        if block:
            db.delete(block)
            db.commit()

            # إرسال إشعار بالبريد الإلكتروني عن إلغاء الحظر
            blocker = db.query(models.User).filter(models.User.id == blocker_id).first()
            blocked = db.query(models.User).filter(models.User.id == blocked_id).first()
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "تم إلغاء الحظر",
                    f"لقد تم إلغاء الحظر عنك من قبل المستخدم {blocker.username}.",
                )
    finally:
        db.close()


@celery_app.task
def clean_expired_blocks():
    db = SessionLocal()
    try:
        expired_blocks = (
            db.query(models.Block).filter(models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)

            # إرسال إشعار بالبريد الإلكتروني عن انتهاء الحظر
            blocker = (
                db.query(models.User).filter(models.User.id == block.blocker_id).first()
            )
            blocked = (
                db.query(models.User).filter(models.User.id == block.blocked_id).first()
            )
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "انتهاء مدة الحظر",
                    f"لقد انتهت مدة الحظر المفروض عليك من قبل المستخدم {blocker.username}.",
                )

        db.commit()
    finally:
        db.close()


# إعداد جدول المهام الدورية
celery_app.conf.beat_schedule = {
    "clean-expired-blocks": {
        "task": "app.celery_worker.clean_expired_blocks",
        "schedule": 3600.0,  # كل ساعة
    },
}


# مثال على مهمة أخرى
@celery_app.task
def some_other_task(data):
    """
    مثال على مهمة أخرى يمكن معالجتها بواسطة Celery.
    """
    # قم بتنفيذ المهام هنا
    pass


@celery_app.task
def calculate_ban_effectiveness():
    db = SessionLocal()
    try:
        # هذا مجرد مثال بسيط. قد تحتاج إلى تعديله بناءً على معايير محددة لتطبيقك
        today = date.today()
        yesterday = today - timedelta(days=1)

        yesterday_stats = (
            db.query(models.BanStatistics)
            .filter(models.BanStatistics.date == yesterday)
            .first()
        )
        if yesterday_stats:
            total_content = db.query(
                func.count(models.Post.id) + func.count(models.Comment.id)
            ).scalar()
            reported_content = (
                db.query(func.count(models.Report.id))
                .filter(models.Report.created_at >= yesterday)
                .scalar()
            )

            effectiveness = (
                1 - (reported_content / total_content) if total_content > 0 else 0
            )
            yesterday_stats.effectiveness_score = effectiveness
            db.commit()
    finally:
        db.close()


# إضافة المهمة إلى جدول celery
celery_app.conf.beat_schedule["calculate-ban-effectiveness"] = {
    "task": "app.celery_worker.calculate_ban_effectiveness",
    "schedule": crontab(hour=0, minute=5),  # تشغيل في الساعة 00:05 كل يوم
}


@celery_app.task
def remove_expired_bans():
    db = SessionLocal()
    try:
        expired_bans = (
            db.query(models.User)
            .filter(models.User.current_ban_end < datetime.now())
            .all()
        )
        for user in expired_bans:
            user.current_ban_end = None
        db.commit()
    finally:
        db.close()


# أضف هذه المهمة إلى جدول المهام
celery_app.conf.beat_schedule["remove-expired-bans"] = {
    "task": "app.celery_worker.remove_expired_bans",
    "schedule": 3600.0,  # كل ساعة
}


@celery_app.task
def reset_report_counters():
    db = SessionLocal()
    try:
        db.query(models.User).update(
            {models.User.total_reports: 0, models.User.valid_reports: 0}
        )
        db.commit()
    finally:
        db.close()


# أضف هذه المهمة إلى جدول المهام
celery_app.conf.beat_schedule["reset-report-counters"] = {
    "task": "app.celery_worker.reset_report_counters",
    "schedule": crontab(day_of_month=1, hour=0, minute=0),  # تشغيل في بداية كل شهر
}


@celery_app.task
def schedule_post_publication(post_id: int):
    db = SessionLocal()
    try:
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if post and not post.is_published:
            post.is_published = True
            db.commit()

            # إرسال الإشعارات ومشاركة المنشور
            user = db.query(models.User).filter(models.User.id == post.owner_id).first()
            send_notifications_and_share(None, post, user)
    finally:
        db.close()
