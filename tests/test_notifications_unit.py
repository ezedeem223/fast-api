"""Focused tests for the notification helper utilities."""

import pytest

from fastapi import BackgroundTasks

from app.notifications import send_email_notification


@pytest.mark.asyncio
async def test_send_email_notification_handles_missing_recipients():
    """The helper should quietly skip sending when no recipients are provided."""

    await send_email_notification(subject="Test", body="No recipients")


@pytest.mark.asyncio
async def test_send_email_notification_schedules_background_task():
    """Supplying background tasks should not raise errors even without SMTP connectivity."""

    captured = {}

    class DummyBackgroundTasks(BackgroundTasks):
        def add_task(self, func, *args, **kwargs):  # type: ignore[override]
            captured["func"] = func
            captured["args"] = args
            captured["kwargs"] = kwargs

    background_tasks = DummyBackgroundTasks()
    await send_email_notification(
        background_tasks=background_tasks,
        to="user@example.com",
        subject="Background",
        body="Testing",
    )

    assert captured["func"] is not None
    assert captured["args"]
