"""Additional coverage for notification service branches."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from app import models as legacy_models
from app.modules.notifications import models as notification_models
from app.modules.notifications import schemas as notification_schemas
from app.modules.notifications import service as notification_service
from app.modules.notifications.common import delivery_status_cache


def _clear_notification_caches():
    notification_service.notification_cache.clear()
    notification_service.priority_notification_cache.clear()
    delivery_status_cache.clear()


def test_publish_realtime_broadcast_swallow_errors(monkeypatch):
    """Ensure publish errors are swallowed."""
    monkeypatch.setenv("REALTIME_REDIS_URL", "redis://example")
    monkeypatch.setenv("REALTIME_REDIS_CHANNEL", "realtime:test")

    class FakeRedis:
        def publish(self, *_):
            raise RuntimeError("fail")

    class FakeRedisModule:
        @staticmethod
        def from_url(_):
            return FakeRedis()

    monkeypatch.setattr(notification_service, "redis", FakeRedisModule())
    notification_service._redis_client = None

    notification_service._publish_realtime_broadcast({"type": "test"})
    assert isinstance(notification_service._redis_client, FakeRedis)


@pytest.mark.asyncio
async def test_delivery_manager_language_and_fallback_commit(monkeypatch, session):
    """Cover translation path and fallback commit in delivery error handling."""
    _clear_notification_caches()
    user = legacy_models.User(email="notify@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    prefs = notification_models.NotificationPreferences(user_id=user.id)
    prefs.auto_translate = True
    prefs.preferred_language = "ar"
    session.add(prefs)

    notification = notification_models.Notification(
        user_id=user.id,
        content="hello",
        notification_type="system",
    )
    notification.language = "en"
    session.add(notification)
    session.commit()
    session.refresh(notification)

    manager = notification_service.NotificationDeliveryManager(session)

    async def fake_translate(content, *_):
        return f"{content}-translated"

    monkeypatch.setattr(notification_service, "get_translated_content", fake_translate)

    translated = await manager._process_language(
        notification.content, notification.language, prefs
    )
    assert translated.endswith("translated")

    async def boom(*_, **__):
        raise RuntimeError("fail")

    manager.max_retries = math.nan
    monkeypatch.setattr(manager, "_process_language", boom)

    result = await manager.deliver_notification(notification)
    assert result is False


@pytest.mark.asyncio
async def test_delivery_manager_update_status_commit_failure():
    """Cover commit failure handling in _update_delivery_status."""
    class FakeDB:
        def __init__(self):
            self.rolled = False

        def add(self, *_):
            return None

        def commit(self):
            raise RuntimeError("fail")

        def rollback(self):
            self.rolled = True

    manager = notification_service.NotificationDeliveryManager(FakeDB())
    notification = notification_models.Notification(id=1)
    with pytest.raises(RuntimeError):
        await manager._update_delivery_status(notification, True, [])
    assert manager.db.rolled is True


@pytest.mark.asyncio
async def test_delivery_manager_preferences_and_email_paths(monkeypatch, session):
    """Cover preference caching and email send branches."""
    _clear_notification_caches()
    user = legacy_models.User(email="mail@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    manager = notification_service.NotificationDeliveryManager(session)

    prefs = manager._get_user_preferences(user.id)
    assert prefs.user_id == user.id
    cached = manager._get_user_preferences(user.id)
    assert cached is prefs

    missing_notification = notification_models.Notification(user_id=9999, content="x")
    await manager._send_email_notification(missing_notification, "body")

    tasks = BackgroundTasks()
    manager.background_tasks = tasks

    async def fake_email(*_, **__):
        return None

    monkeypatch.setattr(notification_service, "send_email_notification", fake_email)
    await manager._send_email_notification(
        notification_models.Notification(user_id=user.id, content="x", notification_type="system"),
        "body",
    )
    assert tasks.tasks

    async def boom(*_, **__):
        raise RuntimeError("boom")

    manager.background_tasks = None
    monkeypatch.setattr(notification_service, "send_email_notification", boom)
    await manager._send_email_notification(
        notification_models.Notification(user_id=user.id, content="x", notification_type="system"),
        "body",
    )


@pytest.mark.asyncio
async def test_delivery_manager_push_paths(monkeypatch, session):
    """Cover push delivery branches for missing devices and success_count logs."""
    sent = []

    class DummyAttr:
        def __eq__(self, _):
            return True

        def is_(self, _):
            return True

    class FakeDevice:
        def __init__(self, token):
            self.fcm_token = token

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *_, **__):
            return self

        def all(self):
            return self.items

    class FakeDB:
        def __init__(self, devices):
            self.devices = devices

        def query(self, *_):
            return FakeQuery(self.devices)

    monkeypatch.setattr(
        notification_service,
        "legacy_models",
        SimpleNamespace(
            UserDevice=SimpleNamespace(user_id=DummyAttr(), is_active=DummyAttr())
        ),
    )
    manager = notification_service.NotificationDeliveryManager(FakeDB([]))

    no_device_notification = notification_models.Notification(
        user_id=1,
        content="push",
        notification_type="system",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
    )
    await manager._send_push_notification(no_device_notification, "body")
    assert sent == []

    manager.db = FakeDB([FakeDevice("token")])

    class FakeResponse:
        success_count = 1

    def fake_send(tokens, title, body, data=None):
        sent.append((tokens, title, body, data))
        return FakeResponse()

    monkeypatch.setattr(notification_service, "send_multicast_notification", fake_send)
    await manager._send_push_notification(no_device_notification, "body")
    assert sent and sent[0][0] == ["token"]


@pytest.mark.asyncio
async def test_retry_delivery_and_final_failure(monkeypatch, session):
    """Cover retry_delivery early returns and refresh failure handling."""
    user = legacy_models.User(email="retry@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    manager = notification_service.NotificationDeliveryManager(session)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(notification_service, "get_model_by_id", lambda *_: None)
    await manager.retry_delivery(notification_id=999, delay=0)

    notification = notification_models.Notification(
        user_id=user.id,
        content="x",
        notification_type="system",
        status=notification_models.NotificationStatus.RETRYING,
    )
    session.add(notification)
    session.commit()
    session.refresh(notification)

    async def fake_deliver(_):
        return True

    monkeypatch.setattr(notification_service, "get_model_by_id", lambda *_: notification)
    monkeypatch.setattr(manager, "deliver_notification", fake_deliver)
    await manager.retry_delivery(notification_id=notification.id, delay=0)
    assert notification.status == notification_models.NotificationStatus.DELIVERED

    def boom_refresh(*_):
        raise RuntimeError("refresh fail")

    monkeypatch.setattr(session, "refresh", boom_refresh)
    await manager._handle_final_failure(notification, {"x": "y"})


def test_notification_service_filters_and_groups(session):
    """Cover preference filtering, grouping, and scheduling helper."""
    _clear_notification_caches()
    user = legacy_models.User(email="prefs@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    prefs = notification_models.NotificationPreferences(
        user_id=user.id,
        quiet_hours_start=datetime.now().time(),
        quiet_hours_end=(datetime.now() + timedelta(minutes=1)).time(),
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
        categories_preferences={},
    )
    session.add(prefs)
    session.commit()

    service = notification_service.NotificationService(session, BackgroundTasks())

    assert service._should_send_notification(
        prefs, notification_models.NotificationCategory.SYSTEM
    ) is False

    prefs.quiet_hours_start = None
    prefs.quiet_hours_end = None
    assert service._should_send_notification(
        prefs, notification_models.NotificationCategory.SYSTEM
    ) is False

    prefs.email_notifications = True
    notification_service.priority_notification_cache[
        f"category_pref_{prefs.user_id}_{notification_models.NotificationCategory.SYSTEM.value}"
    ] = True
    assert service._should_send_notification(
        prefs, notification_models.NotificationCategory.SYSTEM
    ) is True

    class FakeGroup:
        group_type = "group_type"
        user_id = "user_id"
        related_id = "related_id"

        def __init__(self, group_type, user_id, related_id=None, **kwargs):
            self.group_type = group_type
            self.user_id = user_id
            self.related_id = related_id
            self.count = 1
            self.last_updated = None

    class FakeQuery:
        def __init__(self, db):
            self.db = db

        def filter(self, *_, **__):
            return self

        def first(self):
            return self.db.existing

    class FakeDB:
        def __init__(self):
            self.existing = None

        def query(self, *_):
            return FakeQuery(self)

        def add(self, obj):
            self.existing = obj

        def commit(self):
            return None

        def refresh(self, *_):
            return None

        def rollback(self):
            return None

    fake_db = FakeDB()
    fake_service = notification_service.NotificationService(fake_db)
    fake_service.db = fake_db
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(notification_service.notification_models, "NotificationGroup", FakeGroup)

    group = fake_service._find_or_create_group("system", user.id, None)
    assert group is not None
    existing = fake_service._find_or_create_group("system", user.id, None)
    assert existing is not None and existing.count >= 1
    monkeypatch.undo()

    scheduled = notification_models.Notification(
        user_id=user.id,
        content="scheduled",
        notification_type="system",
        scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service._schedule_delivery(scheduled)
    assert service.background_tasks.tasks


@pytest.mark.asyncio
async def test_notification_feed_and_marking(session):
    """Exercise feed cursor handling, mark_as_read, archive, delete, and seen updates."""
    _clear_notification_caches()
    user = legacy_models.User(email="feed@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    service = notification_service.NotificationService(session)

    notification = notification_models.Notification(
        user_id=user.id,
        content="a",
        notification_type="system",
        seen_at=datetime.now(),
    )
    unseen = notification_models.Notification(
        user_id=user.id,
        content="b",
        notification_type="system",
    )
    session.add(notification)
    session.add(unseen)
    session.commit()
    session.refresh(notification)

    feed = await service.get_notification_feed(
        user_id=user.id,
        cursor=notification.id + 1,
        mark_seen=False,
    )
    assert feed["notifications"]

    feed_marked = await service.get_notification_feed(
        user_id=user.id,
        mark_seen=True,
    )
    assert feed_marked["last_seen_at"] is not None

    with pytest.raises(HTTPException):
        await service.mark_as_read(notification_id=9999, user_id=user.id)
    with pytest.raises(HTTPException):
        await service.archive_notification(notification_id=9999, user_id=user.id)
    with pytest.raises(HTTPException):
        await service.delete_notification(notification_id=9999, user_id=user.id)

    assert await service.get_user_preferences(user.id)

    assert service._mark_notifications_seen([], mark_read=False) is None
    notification.status = notification_models.NotificationStatus.DELIVERED
    notification.is_read = True
    notification.seen_at = datetime.now(timezone.utc)
    assert service._mark_notifications_seen([notification], mark_read=False) is None


@pytest.mark.asyncio
async def test_bulk_create_and_retry_paths(monkeypatch, session):
    """Cover bulk_create cache_fragment errors and retry_failed_notification branches."""
    _clear_notification_caches()
    user = legacy_models.User(email="bulk@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    service = notification_service.NotificationService(session)

    payload = notification_schemas.NotificationCreate(
        user_id=user.id,
        content="hi",
        notification_type="system",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        metadata={"bad": object()},
    )

    monkeypatch.setattr(service, "_should_send_notification", lambda *_: False)
    created = await service.bulk_create_notifications([payload])
    assert created == [None]

    with pytest.raises(HTTPException):
        await service.retry_failed_notification(notification_id=9999)

    ok_notification = notification_models.Notification(
        user_id=user.id,
        content="x",
        notification_type="system",
        status=notification_models.NotificationStatus.DELIVERED,
    )
    session.add(ok_notification)
    session.commit()

    result = await service.retry_failed_notification(notification_id=ok_notification.id)
    assert result is False


@pytest.mark.asyncio
async def test_delivery_statistics_and_create_notification_error(monkeypatch, session):
    """Cover delivery statistics aggregation and create_notification error handling."""
    service = notification_service.NotificationService(session)
    monkeypatch.setattr(service.repository, "delivery_log_total", lambda: 3)
    monkeypatch.setattr(service.repository, "delivery_log_counts", lambda status: 1)
    stats = await service.get_delivery_statistics()
    assert stats["pending"] == 1

    class BrokenSession:
        def add(self, *_):
            return None

        def commit(self):
            raise RuntimeError("db")

        def rollback(self):
            return None

    with pytest.raises(RuntimeError):
        notification_service.create_notification(
            BrokenSession(),
            user_id=1,
            content="x",
            link="",
            notification_type="system",
        )
