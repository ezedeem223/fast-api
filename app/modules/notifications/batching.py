"""Batch processing helpers for notifications."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List

from fastapi_mail import MessageSchema

from app.firebase_config import send_multicast_notification

from .common import logger
from .email import send_email_notification


class NotificationBatcher:
    """Batch processor for notifications.

    Supports short-lived batching (to coalesce bursts) and digest-style
    batching for daily/periodic digests.
    """

    def __init__(
        self,
        max_batch_size: int = 100,
        max_wait_time: float = 1.0,
        *,
        digest_window_seconds: float = 86_400.0,
        digest_max_size: int = 50,
    ) -> None:
        self.batch = []
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self._lock = asyncio.Lock()
        self._last_flush = datetime.now(timezone.utc)

        # Digest buffers (per-recipient) for daily summaries.
        self.digest_window_seconds = digest_window_seconds
        self.digest_max_size = digest_max_size
        self._digest_batches: Dict[str, List[dict]] = {}
        self._digest_last_flush: Dict[str, datetime] = {}
        self._digest_lock = asyncio.Lock()

    async def add(self, notification: dict) -> None:
        """Add a notification to the burst batch and flush if thresholds are reached."""
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

    async def add_digest(self, notification: dict) -> None:
        """Queue a notification for the daily/periodic digest."""
        recipient = notification.get("recipient")
        if not recipient:
            return

        to_flush: List[dict] | None = None
        now = datetime.now(timezone.utc)
        async with self._digest_lock:
            bucket = self._digest_batches.setdefault(recipient, [])
            bucket.append(notification)
            last_flush = self._digest_last_flush.get(recipient, now)
            elapsed = (now - last_flush).total_seconds()
            if (
                len(bucket) >= self.digest_max_size
                or elapsed >= self.digest_window_seconds
            ):
                to_flush = list(bucket)
                self._digest_batches[recipient] = []
                self._digest_last_flush[recipient] = now
        if to_flush:
            await self._send_digest_email(recipient, to_flush)

    async def flush(self) -> None:
        """Flush the current burst batch."""
        notifications_to_send = None
        async with self._lock:
            if not self.batch:
                return
            notifications_to_send = self.batch
            self.batch = []
            self._last_flush = datetime.now(timezone.utc)
        await self._process_batch(notifications_to_send)

    async def flush_digests(self) -> None:
        """Flush all pending digest buckets."""
        digests = []
        async with self._digest_lock:
            if not self._digest_batches:
                return
            for recipient, bucket in self._digest_batches.items():
                if bucket:
                    digests.append((recipient, list(bucket)))
            self._digest_batches = {}
            self._digest_last_flush = {}
        for recipient, bucket in digests:
            await self._send_digest_email(recipient, bucket)

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

    async def _send_digest_email(
        self, recipient: str, notifications: List[dict]
    ) -> None:
        """Send a digest email that summarizes multiple notifications."""
        message = MessageSchema(
            subject="Your notification digest",
            recipients=[recipient],
            body=self._format_digest_email(notifications),
            subtype="html",
        )
        await send_email_notification(message)

    async def _send_batch_push(self, notifications: List[dict]) -> None:
        """Send batched push notifications grouped by device tokens."""
        grouped: Dict[tuple[str, ...], List[dict]] = {}
        for notif in notifications:
            tokens = notif.get("tokens") or notif.get("device_tokens") or []
            tokens = [token for token in tokens if token]
            if not tokens:
                logger.info("Skipping push batch item without device tokens.")
                continue
            grouped.setdefault(tuple(tokens), []).append(notif)

        for tokens, batch in grouped.items():
            title = "New Notifications"
            if len(batch) == 1 and batch[0].get("title"):
                title = str(batch[0]["title"])
            body = self._format_batch_push(batch)
            data = {"batch_size": str(len(batch))}
            ids = [str(item.get("id")) for item in batch if item.get("id") is not None]
            if ids:
                data["notification_ids"] = ",".join(ids[:50])
            send_multicast_notification(list(tokens), title, body, data=data)

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

    @staticmethod
    def _format_digest_email(notifications: List[dict]) -> str:
        """Return HTML for digest-style notifications (typically daily)."""
        lines = []
        for n in notifications:
            timestamp = n.get("created_at") or datetime.now(timezone.utc).isoformat()
            lines.append(
                f"<div><h3>{n.get('title','Update')}</h3>"
                f"<p>{n.get('content','')}</p>"
                f"<small>{timestamp}</small></div>"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_batch_push(notifications: List[dict]) -> str:
        """Return a concise push body for a batch."""
        if len(notifications) == 1:
            return (
                str(notifications[0].get("content"))
                if notifications[0].get("content")
                else "You have a new notification."
            )
        titles = [
            str(n.get("title") or n.get("content") or "")
            for n in notifications
            if n.get("title") or n.get("content")
        ]
        if not titles:
            return f"You have {len(notifications)} new notifications."
        preview = "; ".join(titles[:3])
        if len(titles) > 3:
            preview = f"{preview}..."
        return preview


__all__ = ["NotificationBatcher"]
