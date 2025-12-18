import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from app.modules.notifications import models as notification_models
from app.modules.notifications.tasks import (
    deliver_notification_task,
    send_push_notification_task,
)
from app.modules.notifications import realtime


def _notification(session, user_id: int) -> notification_models.Notification:
    notif = notification_models.Notification(
        user_id=user_id,
        content="hi",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)
    return notif


def test_deliver_notification_task_handles_channel_failures(session, test_user, caplog):
    notif = _notification(session, test_user["id"])
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=False,
    )
    session.add(prefs)
    session.commit()

    def email_sender(_):
        raise RuntimeError("smtp down")

    pushed = []

    def push_sender(notification_id: int):
        pushed.append(notification_id)

    deliver_notification_task(session, notif.id, email_sender, push_sender)
    assert pushed == [notif.id]
    assert any("smtp down" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_send_real_time_notification_logs_on_error(monkeypatch, caplog):
    send_mock = AsyncMock(side_effect=RuntimeError("ws down"))
    monkeypatch.setattr(realtime.manager, "send_personal_message", send_mock)
    with pytest.raises(RuntimeError):
        await realtime.send_real_time_notification(1, "msg")
    assert "ws down" in caplog.text
