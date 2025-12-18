"""Batch processing helpers for notifications."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

from fastapi_mail import MessageSchema

from .email import send_email_notification


class NotificationBatcher:
    """Batch processor for notifications."""

    def __init__(self, max_batch_size: int = 100, max_wait_time: float = 1.0) -> None:
        self.batch = []
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self._lock = asyncio.Lock()
        self._last_flush = datetime.now(timezone.utc)

    async def add(self, notification: dict) -> None:
        """Add a notification to the batch and flush if thresholds are reached."""
        notifications_to_send = None
        now = datetime.now(timezone.utc)
        async with self._lock:
            self.batch.append(notification)
            elapsed = (now - self._last_flush).total_seconds()
            if len(self.batch) >= self.max_batch_size or elapsed >= self.max_wait_time:
                notifications_to_send = self.batch
                self.batch = []
                self._last_flush = now
        if notifications_to_send:
            await self._process_batch(notifications_to_send)

    async def flush(self) -> None:
        """Flush the current batch."""
        notifications_to_send = None
        async with self._lock:
            if not self.batch:
                return
            notifications_to_send = self.batch
            self.batch = []
            self._last_flush = datetime.now(timezone.utc)
        await self._process_batch(notifications_to_send)

    async def _process_batch(self, notifications: List[dict]) -> None:
        """Process notifications grouped by channel."""
        email_notifications: List[dict] = []
        push_notifications: List[dict] = []
        in_app_notifications: List[dict] = []

        for notif in notifications:
            channel = notif.get("channel")
            if channel == "email":
                email_notifications.append(notif)
            elif channel == "push":
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
        """Send batched emails grouped by recipient."""
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

    async def _send_batch_push(self, notifications: List[dict]) -> None:
        """Placeholder for batched push delivery (implementation pending)."""
        # TODO: integrate push batching with Firebase/admin SDK
        _ = notifications

    async def _send_batch_in_app(self, notifications: List[dict]) -> None:
        """Placeholder for batched in-app delivery (implementation pending)."""
        _ = notifications

    @staticmethod
    def _format_batch_email(notifications: List[dict]) -> str:
        """Return HTML for batched notifications."""
        return "\n".join(
            [
                f"<div><h3>{n['title']}</h3><p>{n['content']}</p></div>"
                for n in notifications
            ]
        )


__all__ = ["NotificationBatcher"]
