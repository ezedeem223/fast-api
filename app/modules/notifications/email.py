"""Email delivery utilities for notifications."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, List, Optional, Union

from fastapi import BackgroundTasks
from fastapi_mail import MessageSchema
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings, fm
from app.core.database import get_db
from .common import get_model_by_id, handle_async_errors, logger


def queue_email_notification(
    background_tasks: Optional[BackgroundTasks],
    *,
    to: Union[str, List[str]],
    subject: str,
    body: str,
) -> None:
    """Queue an email notification via FastAPI background tasks."""
    task_target: Optional[BackgroundTasks] = background_tasks
    if task_target is None:
        task_target = BackgroundTasks()

    task_target.add_task(
        send_email_notification,
        to=to,
        subject=subject,
        body=body,
    )


def schedule_email_notification(
    background_tasks: Optional[BackgroundTasks],
    *,
    to: Union[str, List[str]],
    subject: str,
    body: str,
) -> None:
    """Compatibility helper that currently queues the notification immediately."""
    queue_email_notification(
        background_tasks,
        to=to,
        subject=subject,
        body=body,
    )


@handle_async_errors
async def send_email_notification(
    message: Optional[MessageSchema] = None,
    *,
    to: Union[str, List[str], None] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    subtype: str = "plain",
) -> None:
    """
    Send an email using FastAPI-Mail. Acts as a no-op in test/dev without credentials.
    """
    if settings.environment.lower() == "test" or os.getenv(
        "DISABLE_EXTERNAL_NOTIFICATIONS"
    ) == "1":
        logger.info("Email sending skipped in test environment.")
        return

    if message is None:
        if to is None:
            raise ValueError("Recipient e-mail address is required.")
        recipients = [to] if isinstance(to, str) else list(to)
        if not recipients:
            raise ValueError("At least one recipient is required.")
        message = MessageSchema(
            subject=subject or "",
            recipients=recipients,
            body=body or "",
            subtype=subtype,
        )

    if not settings.mail_username or not settings.mail_password:
        logger.info(
            "Mail credentials are not configured; skipping send for recipients %s",
            getattr(message, "recipients", []),
        )
        return

    await fm.send_message(message)
    logger.info("Email notification sent successfully")


def schedule_email_notification_by_id(notification_id: int, delay: int = 60) -> None:
    """
    Schedule an email notification by database id for future delivery.
    """
    logger.info(
        "Scheduled email notification %s to be sent in %s seconds.",
        notification_id,
        delay,
    )

    async def task() -> None:
        await asyncio.sleep(delay)
        db_session = next(get_db())
        try:
            notification = get_model_by_id(db_session, models.Notification, notification_id)
            if not notification:
                return

            user = get_model_by_id(db_session, models.User, notification.user_id)
            if user and user.email:
                message = MessageSchema(
                    subject=f"Notification: {notification.notification_type.replace('_',' ').title()}",
                    recipients=[user.email],
                    body=notification.content,
                    subtype="html",
                )
                await send_email_notification(message)
                logger.info("Scheduled email notification %s delivered.", notification_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error in scheduled email notification: %s", exc)
        finally:
            db_session.close()

    asyncio.create_task(task())


@handle_async_errors
async def send_mention_notification(to: str, mentioner: str, post_id: int) -> None:
    """Send an email when a user is mentioned."""
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
    logger.info("Mention notification sent to %s", to)


@handle_async_errors
async def send_login_notification(
    email: str, ip_address: str, user_agent: str
) -> None:
    """Send a security notification when a new login is detected."""
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
    logger.info("Login notification sent to %s", email)


__all__ = [
    "queue_email_notification",
    "schedule_email_notification",
    "send_email_notification",
    "schedule_email_notification_by_id",
    "send_mention_notification",
    "send_login_notification",
]
