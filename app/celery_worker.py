"""Celery worker configuration and tasks.

Execution modes:
- Default: uses broker/backend from `settings` (e.g., Redis) with beat schedule enabled.
- Test: switches to in-memory broker/backend with eager execution so no external services are needed.

Notes:
- Beat schedule wires multiple periodic jobs; adjust intervals with care to avoid duplicate work in multi-worker setups.
- Tasks are thin wrappers around service functions to keep DB session lifecycle explicit.
- The __wrapped__ assignment is kept for compatibility with inspection/mocking in tests and monitoring.
"""

import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
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


# from .routers.post import send_notifications_and_share


# ------------------------- Celery Setup -------------------------
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BACKEND_URL,
)


def _is_test_env() -> bool:
    return (
        settings.environment.lower() == "test"
        or os.getenv("APP_ENV", "").lower() == "test"
        or os.getenv("PYTEST_CURRENT_TEST") is not None
    )


if _is_test_env():
    # Use in-memory broker/backend and eager mode to avoid external services in tests.
    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=True,
        task_eager_propagates=True,
        beat_schedule={},
    )
else:
    # Ensure __wrapped__ exists for tests/monitors that introspect the original function
    for name in [
        "cleanup_old_notifications",
        "process_scheduled_notifications",
        "deliver_notification",
        "send_push_notification",
        "update_notification_analytics",
        "check_old_posts_content",
        "unblock_user",
        "clean_expired_blocks",
        "some_other_task",
        "calculate_ban_effectiveness",
        "remove_expired_bans",
        "reset_report_counters",
        "schedule_post_publication",
    ]:
        if name in globals():
            func = globals()[name]
            try:
                func.__wrapped__ = func  # type: ignore[attr-defined]
            except Exception:
                pass

# ------------------------- Email Configuration -------------------------
fm = FastMail(settings.mail_config)

# ------------------------- Beat Schedule Configuration -------------------------
# Periodic tasks rely on broker being available; keep frequencies conservative to avoid stampedes.
celery_app.conf.beat_schedule = {
    "check-old-posts-content": {
        "task": "app.celery_worker.check_old_posts_content",
        "schedule": crontab(hour=3, minute=0),  # Run daily at 03:00
    },
    "cleanup-old-notifications": {
        "task": "app.celery_worker.cleanup_old_notifications",
        "schedule": crontab(hour=0, minute=0),  # Run daily at midnight
    },
    "process-scheduled-notifications": {
        "task": "app.celery_worker.process_scheduled_notifications",
        "schedule": 60.0,  # Run every minute
    },
    "update-notification-analytics": {
        "task": "app.celery_worker.update_notification_analytics",
        "schedule": crontab(hour="*/1"),  # Run hourly
    },
    "clean-expired-blocks": {
        "task": "app.celery_worker.clean_expired_blocks",
        "schedule": 3600.0,  # Run hourly
    },
    "calculate-ban-effectiveness": {
        "task": "app.celery_worker.calculate_ban_effectiveness",
        "schedule": crontab(hour=0, minute=5),  # Run daily at 00:05
    },
    "remove-expired-bans": {
        "task": "app.celery_worker.remove_expired_bans",
        "schedule": 3600.0,  # Run hourly
    },
    "reset-report-counters": {
        "task": "app.celery_worker.reset_report_counters",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),  # Run monthly on day 1 at 00:00
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
    """Archive read notifications older than 30 days and delete archived ones older than 90 days."""
    db: Session = SessionLocal()
    try:
        cleanup_old_notifications_task(db)
    finally:
        db.close()


@celery_app.task
def process_scheduled_notifications():
    """Fetch scheduled notifications, enqueue delivery tasks, and mark them delivered."""
    db: Session = SessionLocal()
    try:
        process_scheduled_notifications_task(
            db, enqueue_delivery=lambda notification_id: deliver_notification.delay(notification_id)
        )
    finally:
        db.close()


@celery_app.task
def deliver_notification(notification_id: int):
    """Deliver a notification across available channels using injected email/push senders."""
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
    """Send a push notification via Firebase using active user devices."""
    db: Session = SessionLocal()
    try:
        notification_push_handler(db, notification_id)
    finally:
        db.close()


@celery_app.task
def update_notification_analytics():
    """Recompute per-user notification analytics (engagement, response time, peak hours)."""
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
            user_analytics.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@celery_app.task
def send_email_task(email_to: List[EmailStr], subject: str, body: str):
    """Send an email via FastMail.

    Args:
        email_to: List of recipient addresses.
        subject: Email subject.
        body: Email body (supports HTML)."""
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
    """Scan posts for offensive content (delayed check) and flag detected items."""
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
    """Remove a block between two users and notify the previously blocked user."""
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
    """Delete expired blocks and notify affected users."""
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
    """Placeholder Celery task for future expansion."""
    pass


@celery_app.task
def calculate_ban_effectiveness():
    """Calculate a ban-effectiveness score comparing reported content to total content."""
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
    """Clear current_ban_end for users whose bans have expired."""
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
    """Reset monthly report counters for all users."""
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
    """Publish a scheduled post if pending, then trigger notifications/sharing."""
    db: Session = SessionLocal()
    try:
        post = db.query(legacy_models.Post).filter(legacy_models.Post.id == post_id).first()
        if post and not post.is_published:
            post.is_published = True
            db.commit()
            user = db.query(legacy_models.User).filter(legacy_models.User.id == post.owner_id).first()
            from app.routers.post import send_notifications_and_share

            send_notifications_and_share(None, post, user)
    finally:
        db.close()
