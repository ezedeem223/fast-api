import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import celery_worker
from app.modules.notifications import models as notification_models
from app.modules.notifications import batching
from app.modules.notifications import realtime
from app.modules.notifications import common
from app.modules.notifications.tasks import (
    cleanup_old_notifications_task,
    process_scheduled_notifications_task,
    deliver_notification_task,
    send_push_notification_task,
)
from app.modules.notifications.email import send_email_notification


def test_celery_eager_mode_in_test_env():
    assert celery_worker.celery_app.conf.task_always_eager is True
    assert celery_worker.celery_app.conf.task_eager_propagates is True


def test_cleanup_old_notifications_wrapper_closes_session(monkeypatch):
    closed = {"value": False}

    class FakeSession:
        def __init__(self):
            self.committed = False

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def update(self, *_):
            return 1

        def commit(self):
            self.committed = True

        def close(self):
            closed["value"] = True

    fake_session = FakeSession()
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: fake_session)

    celery_worker.cleanup_old_notifications()

    assert closed["value"] is True
    assert fake_session.committed is True


def test_process_scheduled_notifications_marks_delivered_and_calls_delay(monkeypatch):
    called = {"ids": []}
    now = datetime.now(timezone.utc)

    class FakeNotif:
        def __init__(self):
            self.id = 1
            self.scheduled_for = now - timedelta(minutes=1)
            self.status = notification_models.NotificationStatus.PENDING

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *_, **__):
            return self

        def all(self):
            return self.items

    class FakeSession:
        def __init__(self):
            self.notif = FakeNotif()
            self.committed = False

        def query(self, *_, **__):
            return FakeQuery([self.notif])

        def commit(self):
            self.committed = True

        def close(self):
            pass

    fake_session = FakeSession()
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        celery_worker,
        "deliver_notification",
        SimpleNamespace(delay=lambda nid: called["ids"].append(nid)),
    )

    celery_worker.process_scheduled_notifications()

    assert called["ids"] == [1]
    assert fake_session.notif.status == notification_models.NotificationStatus.DELIVERED
    assert fake_session.committed is True


def test_deliver_notification_task_success_calls_channels(session, test_user):
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=False,
    )
    notif = notification_models.Notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
    )
    session.add_all([prefs, notif])
    session.commit()

    email_called = []
    push_called = []

    def email_sender(n):
        email_called.append(n.id)

    def push_sender(nid: int):
        push_called.append(nid)

    deliver_notification_task(session, notif.id, email_sender, push_sender)

    assert email_called == [notif.id]
    assert push_called == [notif.id]


def test_deliver_notification_task_missing_notification_is_noop(session):
    deliver_notification_task(session, 999999, lambda *_: None, lambda *_: None)


def test_send_push_notification_task_logs_on_error(monkeypatch, caplog):
    caplog.clear()

    class FakeNotif:
        def __init__(self):
            self.id = 1
            self.user_id = 7
            self.content = "push me"
            self.notification_type = "system_update"
            self.link = None

    class FakeDevice:
        def __init__(self):
            self.fcm_token = "tok"
            self.is_active = True

    class FakeAttr:
        def __eq__(self, other):
            return True

        def is_(self, other):
            return True

    class FakeLegacy:
        class UserDevice:
            user_id = FakeAttr()
            is_active = FakeAttr()

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def filter(self, *_, **__):
            return self

        def all(self):
            return self._result

    class FakeSession:
        def __init__(self):
            self.notif = FakeNotif()
            self.committed = False

        def get(self, *_, **__):
            return self.notif

        def query(self, *_, **__):
            return FakeQuery([FakeDevice()])

        def commit(self):
            self.committed = True

    fake_session = FakeSession()

    monkeypatch.setattr("app.modules.notifications.tasks.legacy_models", FakeLegacy)
    monkeypatch.setattr(
        "app.modules.notifications.tasks.messaging.send",
        lambda *_: (_ for _ in ()).throw(RuntimeError("fcm down")),  # simulate FCM transport failure
    )

    send_push_notification_task(fake_session, 1)
    assert fake_session.committed is True
    assert any("Error sending push notification" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_notification_batcher_groups_three_emails(monkeypatch):
    sent = {}

    async def fake_send(message):
        sent["body"] = message.body

    monkeypatch.setattr("app.modules.notifications.batching.send_email_notification", fake_send)
    batcher = batching.NotificationBatcher(max_batch_size=3, max_wait_time=10)

    await batcher.add({"channel": "email", "recipient": "a@example.com", "title": "t1", "content": "c1"})
    await batcher.add({"channel": "email", "recipient": "a@example.com", "title": "t2", "content": "c2"})
    await batcher.add({"channel": "email", "recipient": "a@example.com", "title": "t3", "content": "c3"})

    assert "t1" in sent["body"] and "t2" in sent["body"] and "t3" in sent["body"]


@pytest.mark.asyncio
async def test_send_email_notification_raises_on_timeout(monkeypatch):
    monkeypatch.setattr("app.modules.notifications.email.settings.environment", "production")
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")
    monkeypatch.setattr("app.modules.notifications.email.settings.mail_username", "u")
    monkeypatch.setattr("app.modules.notifications.email.settings.mail_password", "p")

    async def boom(_):
        raise TimeoutError("smtp timeout")

    monkeypatch.setattr("app.modules.notifications.email.fm.send_message", boom)

    with pytest.raises(TimeoutError):
        await send_email_notification(
            to="u@example.com", subject="s", body="b", subtype="plain"
        )


@pytest.mark.asyncio
async def test_realtime_prunes_broken_connection(monkeypatch):
    manager = realtime.ConnectionManager()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock(side_effect=RuntimeError("ws break"))

    await manager.connect(ws, user_id=1)
    await manager.send_personal_message({"ping": True}, user_id=1)

    assert manager.active_connections.get(1) == []
