from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi_mail import MessageSchema

from app.notifications import NotificationBatcher, send_email_notification


@pytest.mark.asyncio
async def test_send_email_notification(monkeypatch):
    async_mock = AsyncMock()
    monkeypatch.setattr("app.notifications.fm.send_message", async_mock)
    message = MessageSchema(subject="Hello", recipients=["user@example.com"], body="Hi", subtype="plain")
    await send_email_notification(message)
    async_mock.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_notification_batcher_flushes(monkeypatch):
    batcher = NotificationBatcher(max_batch_size=2, max_wait_time=0.01)
    process_mock = AsyncMock()
    monkeypatch.setattr(batcher, "_process_batch", process_mock)

    await batcher.add({"id": 1})
    await batcher.add({"id": 2})
    process_mock.assert_awaited()
