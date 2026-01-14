"""Test module for test notifications session1 extra."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi_mail import MessageSchema

from app.core.config import settings
from app.modules.notifications import common
from app.modules.notifications import models as notification_models
from app.modules.notifications.batching import NotificationBatcher
from app.modules.notifications.email import (
    queue_email_notification,
    schedule_email_notification,
    schedule_email_notification_by_id,
    send_email_notification,
)
from app.modules.notifications.realtime import ConnectionManager
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.tasks import (
    cleanup_old_notifications_task,
    deliver_notification_task,
    process_scheduled_notifications_task,
)
from fastapi import BackgroundTasks


def test_queue_email_notification_adds_background_task():
    """Test case for test queue email notification adds background task."""
    tasks = BackgroundTasks()
    queue_email_notification(
        tasks,
        to="person@example.com",
        subject="Hi",
        body="Hello there",
    )
    assert tasks.tasks, "Expected background task to be added for email send."


@pytest.mark.asyncio
async def test_send_email_notification_sends_message_object(monkeypatch):
    """Test case for test send email notification sends message object."""
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.environment", "production"
    )
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.mail_username", "user"
    )
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.mail_password", "pass"
    )
    send_mock = AsyncMock()
    monkeypatch.setattr("app.modules.notifications.email.fm.send_message", send_mock)

    msg = MessageSchema(
        subject="hi", recipients=["u@example.com"], body="b", subtype="plain"
    )
    await send_email_notification(message=msg)
    send_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_notification_raises_on_smtp_error(monkeypatch):
    """Test case for test send email notification raises on smtp error."""
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.environment", "production"
    )
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.mail_username", "user"
    )
    monkeypatch.setattr(
        "app.modules.notifications.email.settings.mail_password", "pass"
    )
    send_mock = AsyncMock(side_effect=RuntimeError("smtp down"))
    monkeypatch.setattr("app.modules.notifications.email.fm.send_message", send_mock)

    msg = MessageSchema(
        subject="hi", recipients=["u@example.com"], body="b", subtype="plain"
    )
    with pytest.raises(RuntimeError):
        await send_email_notification(message=msg)


def test_schedule_email_notification_queues(monkeypatch):
    """Test case for test schedule email notification queues."""
    tasks = BackgroundTasks()
    queue = []

    async def dummy_send(**kwargs):
        queue.append(kwargs)

    monkeypatch.setattr(
        "app.modules.notifications.email.send_email_notification", dummy_send
    )
    schedule_email_notification(tasks, to="a@b.com", subject="hi", body="body")
    assert tasks.tasks, "Task should be queued"


@pytest.mark.asyncio
async def test_schedule_email_notification_by_id_delivers(
    monkeypatch, session, test_user
):
    # force production path
    """Test case for test schedule email notification by id delivers."""
    monkeypatch.setattr(settings, "environment", "production")
    notif = notification_models.Notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
    )
    session.add(notif)
    session.commit()

    sent = {"count": 0}

    async def fake_send(message):
        sent["count"] += 1

    monkeypatch.setattr(
        "app.modules.notifications.email.send_email_notification", fake_send
    )
    monkeypatch.setattr(
        "app.modules.notifications.email.get_db", lambda: iter([session])
    )

    created_tasks = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        return coro

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    schedule_email_notification_by_id(notif.id, delay=0)
    assert created_tasks, "expected a scheduled coroutine"
    await created_tasks[0]
    assert sent["count"] == 1


def test_cleanup_old_notifications_task_archives_and_deletes(session, test_user):
    """Test case for test cleanup old notifications task archives and deletes."""
    now = datetime.now(timezone.utc)
    old_read = notification_models.Notification(
        user_id=test_user["id"],
        content="read",
        notification_type="system_update",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        is_read=True,
        created_at=now - timedelta(days=40),
    )
    old_archived = notification_models.Notification(
        user_id=test_user["id"],
        content="archived",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        is_archived=True,
        created_at=now - timedelta(days=100),
    )
    recent = notification_models.Notification(
        user_id=test_user["id"],
        content="recent",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        created_at=now - timedelta(days=5),
    )
    session.add_all([old_read, old_archived, recent])
    session.commit()

    cleanup_old_notifications_task(session, archive_days=30, delete_days=90)

    session.refresh(old_read)
    session.refresh(old_archived)
    session.refresh(recent)
    assert old_read.is_archived is True
    assert old_archived.is_deleted is True
    assert recent.is_archived is False


def test_process_scheduled_notifications_task_marks_delivered(session, test_user):
    """Test case for test process scheduled notifications task marks delivered."""
    now = datetime.now(timezone.utc)
    due = notification_models.Notification(
        user_id=test_user["id"],
        content="due",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        scheduled_for=now - timedelta(minutes=1),
        status=notification_models.NotificationStatus.PENDING,
    )
    future = notification_models.Notification(
        user_id=test_user["id"],
        content="future",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        scheduled_for=now + timedelta(minutes=5),
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add_all([due, future])
    session.commit()
    delivered = []

    def enqueue_delivery(notification_id: int) -> None:
        delivered.append(notification_id)

    process_scheduled_notifications_task(session, enqueue_delivery)

    session.refresh(due)
    session.refresh(future)
    assert delivered == [due.id]
    assert due.status == notification_models.NotificationStatus.DELIVERED
    assert future.status == notification_models.NotificationStatus.PENDING


def test_deliver_notification_task_respects_preferences(session, test_user):
    """Test case for test deliver notification task respects preferences."""
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=True,
    )
    notif = notification_models.Notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
    )
    session.add_all([prefs, notif])
    session.commit()
    email_calls = []
    push_calls = []

    def email_sender(notification):
        email_calls.append(notification.id)

    def push_sender(notification_id: int):
        push_calls.append(notification_id)

    deliver_notification_task(session, notif.id, email_sender, push_sender)

    assert email_calls == [notif.id]
    assert push_calls == [notif.id]


@pytest.mark.asyncio
async def test_connection_manager_cleans_up_broken_connections():
    """Test case for test connection manager cleans up broken connections."""
    manager = ConnectionManager()
    websocket = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.send_json = AsyncMock(side_effect=RuntimeError("boom"))

    await manager.connect(websocket, user_id=1)
    await manager.send_personal_message({"msg": "hi"}, user_id=1)

    assert manager.active_connections.get(1) == []


@pytest.mark.asyncio
async def test_connection_manager_enforces_limit(monkeypatch):
    """Test case for test connection manager enforces limit."""
    manager = ConnectionManager(max_connections_per_user=1)
    ws1 = AsyncMock()
    ws1.accept = AsyncMock()
    ws1.close = AsyncMock()
    await manager.connect(ws1, user_id=7)

    ws2 = AsyncMock()
    ws2.accept = AsyncMock()
    ws2.close = AsyncMock()

    allowed = await manager.connect(ws2, user_id=7)
    assert allowed is False
    ws2.close.assert_awaited()
    assert manager.connection_counts[7] == 1


@pytest.mark.asyncio
async def test_connection_manager_mirrors_presence(monkeypatch):
    """Test case for test connection manager mirrors presence."""
    manager = ConnectionManager()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()

    set_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.notifications.realtime.cache_manager.enabled", True
    )
    monkeypatch.setattr(
        "app.modules.notifications.realtime.cache_manager.redis", object()
    )
    monkeypatch.setattr(
        "app.modules.notifications.realtime.cache_manager.set_with_tags", set_mock
    )

    await manager.connect(ws, user_id=9)
    set_mock.assert_awaited()


def test_get_or_create_and_get_model_by_id(session, test_user, monkeypatch, caplog):
    """Test case for test get or create and get model by id."""
    created = common.get_or_create(
        session,
        notification_models.NotificationPreferences,
        user_id=test_user["id"],
        defaults={"email_notifications": False},
    )
    fetched = common.get_model_by_id(
        session, notification_models.NotificationPreferences, created.id
    )
    assert fetched.id == created.id
    assert fetched.email_notifications is False

    class BoomSession:
        def query(self, *_, **__):
            raise RuntimeError("db down")

    caplog.clear()
    assert (
        common.get_model_by_id(BoomSession(), notification_models.Notification, 1)
        is None
    )
    assert any("db down" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_notification_batcher_flush_and_email_group(monkeypatch):
    """Test case for test notification batcher flush and email group."""
    send_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.notifications.batching.send_email_notification", send_mock
    )
    batcher = NotificationBatcher(max_batch_size=2, max_wait_time=10)

    await batcher.add(
        {
            "channel": "email",
            "recipient": "a@example.com",
            "title": "t1",
            "content": "c1",
        }
    )
    await batcher.add(
        {
            "channel": "email",
            "recipient": "a@example.com",
            "title": "t2",
            "content": "c2",
        }
    )

    send_mock.assert_awaited_once()
    body = send_mock.call_args.args[0].body
    assert "t1" in body and "t2" in body


@pytest.mark.asyncio
async def test_notification_batcher_flush_noop(monkeypatch):
    """Test case for test notification batcher flush noop."""
    send_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.notifications.batching.send_email_notification", send_mock
    )
    batcher = NotificationBatcher()
    await batcher.flush()
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notification_batcher_digest_flush(monkeypatch):
    """Test case for test notification batcher digest flush."""
    send_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.notifications.batching.send_email_notification", send_mock
    )
    batcher = NotificationBatcher(digest_window_seconds=0.01, digest_max_size=5)

    await batcher.add_digest(
        {
            "channel": "email",
            "recipient": "d@example.com",
            "title": "t1",
            "content": "c1",
        }
    )
    await asyncio.sleep(0.02)
    await batcher.add_digest(
        {
            "channel": "email",
            "recipient": "d@example.com",
            "title": "t2",
            "content": "c2",
        }
    )
    await batcher.flush_digests()

    assert send_mock.await_count >= 1
    body = send_mock.call_args.args[0].body
    assert "t1" in body and "t2" in body


def test_notification_repository_filters_and_status(session, test_user):
    """Test case for test notification repository filters and status."""
    repo = NotificationRepository(session)
    now = datetime.now(timezone.utc)
    urgent = repo.create_notification(
        user_id=test_user["id"],
        content="urgent",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.URGENT,
        status=notification_models.NotificationStatus.RETRYING,
        created_at=now,
    )
    old = repo.create_notification(
        user_id=test_user["id"],
        content="old",
        notification_type="system_update",
        category=notification_models.NotificationCategory.PROMOTIONAL,
        priority=notification_models.NotificationPriority.LOW,
        status=notification_models.NotificationStatus.PENDING,
        created_at=now - timedelta(days=2),
    )

    q = repo.build_notifications_query(
        user_id=test_user["id"],
        include_read=True,
        include_archived=True,
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.URGENT,
        status=notification_models.NotificationStatus.RETRYING,
        since=now - timedelta(hours=1),
    )
    results = q.all()
    assert urgent in results
    assert old not in results


def test_notification_repository_cleanup_and_delivery_logs(session, test_user):
    """Test case for test notification repository cleanup and delivery logs."""
    repo = NotificationRepository(session)
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    _ = repo.create_notification(
        user_id=test_user["id"],
        content="arch",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        is_archived=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    repo.create_notification(
        user_id=test_user["id"],
        content="fresh",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        created_at=datetime.now(timezone.utc),
    )
    deleted = repo.cleanup_archived(cutoff)
    assert deleted == 1

    log_notif = repo.create_notification(
        user_id=test_user["id"],
        content="loggable",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
    )
    log1 = notification_models.NotificationDeliveryLog(
        notification_id=log_notif.id, status="delivered"
    )
    log2 = notification_models.NotificationDeliveryLog(
        notification_id=log_notif.id, status="failed"
    )
    session.add_all([log1, log2])
    session.commit()

    assert repo.delivery_log_total() == 2
    assert repo.delivery_log_counts("delivered") == 1
