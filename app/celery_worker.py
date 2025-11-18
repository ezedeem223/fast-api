from collections import Counter
from datetime import date, datetime, timedelta
from typing import List

from celery import Celery
from celery.schedules import crontab
from fastapi_mail import FastMail, MessageSchema
from pydantic import EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app import models as legacy_models
from app.modules.notifications import models as notification_models
from app.modules.notifications.tasks import (
    cleanup_old_notifications_task,
    process_scheduled_notifications_task,
    deliver_notification_task as notification_delivery_handler,
    send_push_notification_task as notification_push_handler,
)
from app.modules.utils.content import is_content_offensive


# إزالة الاستيراد الثابت لدالة send_notifications_and_share لتفادي دائرة الاستيراد
# from .routers.post import send_notifications_and_share


# ------------------------- Celery Setup -------------------------
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BACKEND_URL,
)

# ------------------------- Email Configuration -------------------------
fm = FastMail(settings.mail_config)

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


def calculate_user_notification_analytics(db: Session, user_id: int) -> dict:
    """
    Simple analytics helper used by the scheduled task to avoid None values.
    """
    notifications = (
        db.query(notification_models.Notification)
        .filter(notification_models.Notification.user_id == user_id)
        .all()
    )
    if not notifications:
        return {"engagement_rate": 0.0, "response_time": 0.0, "peak_hours": []}

    total = len(notifications)
    read_count = sum(1 for notification in notifications if notification.is_read)
    response_times = [
        (notification.read_at - notification.created_at).total_seconds()
        for notification in notifications
        if notification.created_at and notification.read_at
    ]
    avg_response = (
        sum(response_times) / len(response_times) if response_times else 0.0
    )
    hours = [notification.created_at.hour for notification in notifications if notification.created_at]
    peak_hours = [hour for hour, _ in Counter(hours).most_common(3)]

    return {
        "engagement_rate": read_count / total if total else 0.0,
        "response_time": avg_response,
        "peak_hours": peak_hours,
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
        cleanup_old_notifications_task(db)
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
        process_scheduled_notifications_task(
            db, enqueue_delivery=lambda notification_id: deliver_notification.delay(notification_id)
        )
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
        notification_delivery_handler(
            db,
            notification_id,
            email_sender=lambda notification: send_email_task.delay(
                [notification.user.email], "New Notification", notification.content
            ),
            push_sender=lambda notif_id: send_push_notification.delay(notif_id),
        )
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
        notification_push_handler(db, notification_id)
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
        users = db.query(legacy_models.User).all()
        for user in users:
            analytics = calculate_user_notification_analytics(db, user.id)
            user_analytics = (
                db.query(notification_models.NotificationAnalytics)
                .filter(notification_models.NotificationAnalytics.user_id == user.id)
                .first()
            )
            if not user_analytics:
                user_analytics = notification_models.NotificationAnalytics(user_id=user.id)
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
        old_posts = (
            db.query(legacy_models.Post)
            .filter(legacy_models.Post.is_flagged.is_(False))
            .all()
        )
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
            db.query(legacy_models.Block)
            .filter(
                legacy_models.Block.blocker_id == blocker_id,
                legacy_models.Block.blocked_id == blocked_id,
            )
            .first()
        )
        if block:
            db.delete(block)
            db.commit()

            blocker = db.query(legacy_models.User).filter(legacy_models.User.id == blocker_id).first()
            blocked = db.query(legacy_models.User).filter(legacy_models.User.id == blocked_id).first()
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
            db.query(legacy_models.Block).filter(legacy_models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)
            blocker = (
                db.query(legacy_models.User).filter(legacy_models.User.id == block.blocker_id).first()
            )
            blocked = (
                db.query(legacy_models.User).filter(legacy_models.User.id == block.blocked_id).first()
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
            db.query(legacy_models.BanStatistics)
            .filter(legacy_models.BanStatistics.date == yesterday)
            .first()
        )
        if yesterday_stats:
            total_content = db.query(
                func.count(legacy_models.Post.id) + func.count(legacy_models.Comment.id)
            ).scalar()
            reported_content = (
                db.query(func.count(legacy_models.Report.id))
                .filter(legacy_models.Report.created_at >= yesterday)
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
            db.query(legacy_models.User)
            .filter(legacy_models.User.current_ban_end < datetime.now())
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
        db.query(legacy_models.User).update(
            {legacy_models.User.total_reports: 0, legacy_models.User.valid_reports: 0}
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
        post = db.query(legacy_models.Post).filter(legacy_models.Post.id == post_id).first()
        if post and not post.is_published:
            post.is_published = True
            db.commit()
            user = db.query(legacy_models.User).filter(legacy_models.User.id == post.owner_id).first()
            # لتفادي دائرة الاستيراد، نستورد دالة send_notifications_and_share محلياً
            from app.routers.post import send_notifications_and_share

            send_notifications_and_share(None, post, user)
    finally:
        db.close()

