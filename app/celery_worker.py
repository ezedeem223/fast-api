from celery import Celery
from celery.schedules import crontab
from fastapi_mail import FastMail, MessageSchema
from pydantic import EmailStr
from typing import List
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings  # استخدام الإعدادات بالحروف الكبيرة كما هو معرف
from app.database import SessionLocal
from app import models
from app.utils import is_content_offensive

# إزالة الاستيراد الثابت لدالة send_notifications_and_share لتفادي دائرة الاستيراد
# from .routers.post import send_notifications_and_share

import firebase_admin
from firebase_admin import credentials, messaging

# ------------------------- Celery Setup -------------------------
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BACKEND_URL,
)

# ------------------------- Email Configuration -------------------------
# استخدام إعدادات البريد الإلكتروني من ملف config.py
from app.config import fm  # fm معرف في config.py

email_conf = settings.mail_config
fm = FastMail(email_conf)

# ------------------------- Beat Schedule Configuration -------------------------
celery_app.conf.beat_schedule = {
    "check-old-posts-content": {
        "task": "app.celery_worker.check_old_posts_content",
        "schedule": crontab(hour=3, minute=0),  # تشغيل يومياً في الساعة 3 صباحاً
    },
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
    "clean-expired-blocks": {
        "task": "app.celery_worker.clean_expired_blocks",
        "schedule": 3600.0,  # تشغيل كل ساعة
    },
    "calculate-ban-effectiveness": {
        "task": "app.celery_worker.calculate_ban_effectiveness",
        "schedule": crontab(hour=0, minute=5),  # تشغيل يومياً الساعة 00:05
    },
    "remove-expired-bans": {
        "task": "app.celery_worker.remove_expired_bans",
        "schedule": 3600.0,  # تشغيل كل ساعة
    },
    "reset-report-counters": {
        "task": "app.celery_worker.reset_report_counters",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),  # تشغيل في بداية كل شهر
    },
}

# ------------------------- Celery Tasks -------------------------


@celery_app.task
def cleanup_old_notifications():
    """
    تنظيف الإشعارات القديمة:
    - أرشفة الإشعارات المقروءة التي مضى عليها أكثر من 30 يومًا.
    - حذف الإشعارات الأقدم من 90 يومًا والتي تمت أرشفتها.
    """
    db: Session = SessionLocal()
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        db.query(models.Notification).filter(
            models.Notification.is_read == True,
            models.Notification.created_at < thirty_days_ago,
            models.Notification.is_archived == False,
        ).update({"is_archived": True})

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
    """
    معالجة الإشعارات المجدولة:
    - استرجاع الإشعارات المجدولة للتسليم.
    - إطلاق تسليمها عبر مهام منفصلة وتحديدها كمُسلمة.
    """
    db: Session = SessionLocal()
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
    """
    تسليم إشعار عبر جميع القنوات المُعدّة وفقًا لتفضيلات المستخدم.
    - إذا كانت الإشعارات عبر البريد الإلكتروني مفعلة، يتم إطلاق مهمة البريد.
    - إذا كانت الإشعارات عبر الدفع مفعلة، يتم إطلاق مهمة الدفع.
    """
    db: Session = SessionLocal()
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

        if user_prefs.email_notifications:
            send_email_task.delay(
                [notification.user.email], "New Notification", notification.content
            )
        if user_prefs.push_notifications:
            send_push_notification.delay(notification_id)
    finally:
        db.close()


@celery_app.task
def send_push_notification(notification_id: int):
    """
    إرسال إشعار دفع باستخدام Firebase.
    يسترجع الأجهزة النشطة للمستخدم ويرسل رسالة الإشعار.
    """
    db: Session = SessionLocal()
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
    """
    تحديث تحليلات الإشعارات لكل مستخدم.
    يحسب معدل التفاعل، ووقت الاستجابة، وساعات الذروة، ويحدث سجل التحليلات.
    """
    db: Session = SessionLocal()
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
    إرسال بريد إلكتروني باستخدام FastMail.

    المعلمات:
    - email_to: قائمة عناوين البريد الإلكتروني للمستلمين.
    - subject: موضوع البريد.
    - body: محتوى البريد (يدعم HTML).
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
    """
    التحقق من محتوى المنشورات القديمة بحثًا عن مواد مسيئة.
    يستخدم أداة ذكاء اصطناعي لتحديد المنشورات التي تحتوي على محتوى قد يكون مسيئًا.
    """
    db: Session = SessionLocal()
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
    """
    رفع الحظر عن مستخدم من خلال حذف سجل الحظر وإرسال إشعار بالبريد الإلكتروني.
    """
    db: Session = SessionLocal()
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

            blocker = db.query(models.User).filter(models.User.id == blocker_id).first()
            blocked = db.query(models.User).filter(models.User.id == blocked_id).first()
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "Unblock Notification",
                    f"You have been unblocked by {blocker.username}.",
                )
    finally:
        db.close()


@celery_app.task
def clean_expired_blocks():
    """
    حذف سجلات الحظر المنتهية وإرسال إشعارات بالبريد الإلكتروني عن انتهاء الحظر.
    """
    db: Session = SessionLocal()
    try:
        expired_blocks = (
            db.query(models.Block).filter(models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)
            blocker = (
                db.query(models.User).filter(models.User.id == block.blocker_id).first()
            )
            blocked = (
                db.query(models.User).filter(models.User.id == block.blocked_id).first()
            )
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "Block Expired",
                    f"Your block imposed by {blocker.username} has expired.",
                )
        db.commit()
    finally:
        db.close()


@celery_app.task
def some_other_task(data):
    """
    مثال لمهمة أخرى يمكن معالجتها بواسطة Celery.
    """
    # تنفيذ العمليات اللازمة مع البيانات المُقدمة
    pass


@celery_app.task
def calculate_ban_effectiveness():
    """
    حساب وتحديث فعالية الحظر استناداً إلى المنشورات والتعليقات والتقارير.
    """
    db: Session = SessionLocal()
    try:
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


@celery_app.task
def remove_expired_bans():
    """
    إزالة الحظر المنتهية عن المستخدمين بإعادة تعيين تاريخ انتهاء الحظر.
    """
    db: Session = SessionLocal()
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


@celery_app.task
def reset_report_counters():
    """
    إعادة تعيين عدادات التقارير لجميع المستخدمين في بداية كل شهر.
    """
    db: Session = SessionLocal()
    try:
        db.query(models.User).update(
            {models.User.total_reports: 0, models.User.valid_reports: 0}
        )
        db.commit()
    finally:
        db.close()


@celery_app.task
def schedule_post_publication(post_id: int):
    """
    نشر منشور مجدول إذا لم يُنشر بعد، ثم تفعيل الإشعارات والمشاركة.
    """
    db: Session = SessionLocal()
    try:
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if post and not post.is_published:
            post.is_published = True
            db.commit()
            user = db.query(models.User).filter(models.User.id == post.owner_id).first()
            # لتفادي دائرة الاستيراد، نستورد دالة send_notifications_and_share محلياً
            from app.routers.post import send_notifications_and_share

            send_notifications_and_share(None, post, user)
    finally:
        db.close()
