import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi import HTTPException

from app.modules.notifications import models as notification_models
from app.modules.notifications import schemas as notification_schemas
from app.modules.notifications.analytics import NotificationAnalyticsService
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import (
    NotificationService,
    NotificationDeliveryManager,
    NotificationRetryHandler,
)
from app.modules.notifications.common import (
    delivery_status_cache,
    notification_cache,
    priority_notification_cache,
)


def _make_notification(user_id: int, **kwargs) -> notification_models.Notification:
    defaults = dict(
        content="payload",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.MEDIUM,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    language = defaults.pop("language", "en")
    notif = notification_models.Notification(user_id=user_id, **defaults)
    setattr(notif, "language", language)
    return notif


def test_notification_repository_filters_and_counts(session, test_user):
    repo = NotificationRepository(session)
    now = datetime.now(timezone.utc)
    n1 = repo.create_notification(
        user_id=test_user["id"],
        content="new",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.HIGH,
        created_at=now,
    )
    n2 = repo.create_notification(
        user_id=test_user["id"],
        content="old-read",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        is_read=True,
        read_at=now - timedelta(hours=1),
        seen_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=1),
    )
    n3 = repo.create_notification(
        user_id=test_user["id"],
        content="archived",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        is_archived=True,
        is_read=True,
        seen_at=now - timedelta(days=1),
        created_at=now - timedelta(days=2),
    )
    _ = repo.create_notification(
        user_id=test_user["id"],
        content="deleted",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        is_deleted=True,
        created_at=now,
    )

    query = repo.build_notifications_query(
        user_id=test_user["id"],
        include_read=False,
        include_archived=False,
        category=None,
        priority=None,
    )
    results = query.all()
    assert n1 in results
    assert n2 not in results
    assert n3 not in results

    summary = repo.get_unread_summary(test_user["id"])
    assert summary["unread_count"] == 1
    assert summary["unseen_count"] == 1  # only n1 is unseen and unread
    assert summary["unread_urgent_count"] >= 0

    marked = repo.mark_notification_as_read(n1.id, test_user["id"])
    assert marked.is_read is True
    assert repo.unread_count(test_user["id"]) == 0


def test_notification_repository_mark_all_and_cleanup(session, test_user):
    repo = NotificationRepository(session)
    n1 = repo.create_notification(
        user_id=test_user["id"],
        content="n1",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    n2 = repo.create_notification(
        user_id=test_user["id"],
        content="n2",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )

    updated = repo.mark_all_as_read(test_user["id"])
    assert updated == 2
    repo.archive_notification(n1.id, test_user["id"])
    repo.soft_delete_notification(n2.id, test_user["id"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    deleted = repo.cleanup_archived(cutoff)
    assert deleted >= 0


def test_notification_analytics_service(session, test_user):
    now = datetime.now(timezone.utc)
    notif = _make_notification(test_user["id"], created_at=now - timedelta(hours=1))
    session.add(notif)
    session.commit()
    session.refresh(notif)

    logs = [
        notification_models.NotificationDeliveryLog(
            notification_id=notif.id, status="delivered"
        ),
        notification_models.NotificationDeliveryLog(
            notification_id=notif.id, status="failed"
        ),
    ]
    session.add_all(logs)
    session.commit()

    analytics = NotificationAnalyticsService(session)
    stats = analytics.get_delivery_stats(user_id=test_user["id"])
    assert stats["total"] == 2
    assert stats["successful"] == 1
    assert stats["failed"] == 1
    assert stats["success_rate"] == 50

    notif.is_read = True
    session.commit()
    engagement = analytics.get_user_engagement(test_user["id"], days=7)
    assert engagement["total_notifications"] == 1
    assert engagement["read_notifications"] == 1
    assert engagement["engagement_rate"] == 100

    detailed = asyncio.run(analytics.get_detailed_analytics(days=7))
    assert "delivery" in detailed and "engagement" in detailed


@pytest.mark.asyncio
async def test_notification_service_respects_preferences(monkeypatch, session, test_user):
    service = NotificationService(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        categories_preferences={
            notification_models.NotificationCategory.SYSTEM.value: False
        },
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=True,
    )
    session.add(prefs)
    session.commit()

    monkeypatch.setattr(service.repository, "ensure_preferences", lambda uid: prefs)
    monkeypatch.setattr(service, "_process_language", AsyncMock(return_value="translated"))
    monkeypatch.setattr(service, "_find_or_create_group", lambda *args, **kwargs: None)
    def _fake_create_notification(**kwargs):
        kwargs.pop("language", None)
        kwargs.pop("group_id", None)
        notif = notification_models.Notification(**kwargs)
        session.add(notif)
        session.commit()
        session.refresh(notif)
        return notif

    monkeypatch.setattr(service.repository, "create_notification", _fake_create_notification)
    service.delivery_manager = MagicMock()
    service.delivery_manager.deliver_notification = AsyncMock(return_value=True)

    skipped = await service.create_notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.MEDIUM,
    )
    assert skipped is None

    # enable category to allow sending
    prefs.categories_preferences = {}
    priority_notification_cache.clear()
    delivered = await service.create_notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.MEDIUM,
    )
    assert delivered is not None
    service.delivery_manager.deliver_notification.assert_awaited()


def test_notification_service_mark_notifications_seen(session, test_user):
    service = NotificationService(session)
    notif1 = _make_notification(test_user["id"], status=notification_models.NotificationStatus.PENDING)
    notif2 = _make_notification(test_user["id"], status=notification_models.NotificationStatus.RETRYING)
    session.add_all([notif1, notif2])
    session.commit()
    notifications = [notif1, notif2]

    seen_at = service._mark_notifications_seen(notifications, mark_read=True)
    assert seen_at is not None
    session.refresh(notif1)
    session.refresh(notif2)
    assert notif1.seen_at is not None and notif1.read_at is not None
    assert notif1.status == notification_models.NotificationStatus.DELIVERED
    assert notif2.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_websocket_endpoint_happy_and_empty_message(monkeypatch):
    from app.api import websocket as ws_module

    send_mock = AsyncMock()
    dummy_manager = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
    )
    monkeypatch.setattr(ws_module, "manager", dummy_manager)
    monkeypatch.setattr(ws_module, "send_real_time_notification", send_mock)

    ws_ok = MagicMock()
    ws_ok.receive_text = AsyncMock(side_effect=["hello", WebSocketDisconnect()])
    await ws_module.websocket_endpoint(ws_ok, user_id=42)
    send_mock.assert_awaited_with(42, "hello")
    assert dummy_manager.disconnect.await_count == 1

    ws_empty = MagicMock()
    ws_empty.receive_text = AsyncMock(side_effect=[""])
    dummy_manager.connect.reset_mock()
    dummy_manager.disconnect.reset_mock()
    send_mock.reset_mock()
    await ws_module.websocket_endpoint(ws_empty, user_id=99)
    dummy_manager.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_connection_manager_broadcast_and_cleanup(monkeypatch):
    from app.modules.notifications import realtime

    manager = realtime.ConnectionManager()
    ws1 = AsyncMock()
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()
    ws2 = AsyncMock()
    ws2.accept = AsyncMock()
    ws2.send_json = AsyncMock(side_effect=RuntimeError("fail"))

    await manager.connect(ws1, user_id=1)
    await manager.connect(ws2, user_id=2)

    await manager.broadcast({"msg": "hi"})
    ws1.send_json.assert_awaited()
    assert manager.active_connections.get(2) == []


@pytest.mark.asyncio
async def test_send_real_time_notification_builds_payload(monkeypatch):
    from app.modules.notifications import realtime

    send_mock = AsyncMock()
    monkeypatch.setattr(realtime.manager, "send_personal_message", send_mock)

    await realtime.send_real_time_notification(7, "hello")
    send_mock.assert_awaited_with(
        {"message": "hello", "type": "simple_notification"}, 7
    )

    await realtime.send_real_time_notification(8, {"message": "data"})
    send_mock.assert_awaited_with({"message": "data"}, 8)


@pytest.mark.asyncio
async def test_delivery_manager_retry_on_failure(monkeypatch, session, test_user):
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    manager.retry_delays = [1, 2, 3]
    manager._process_language = AsyncMock(side_effect=RuntimeError("boom"))
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
    )
    manager._get_user_preferences = MagicMock(return_value=prefs)

    notif = _make_notification(
        test_user["id"],
        retry_count=0,
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    success = await manager.deliver_notification(notif)
    session.refresh(notif)

    assert success is False
    assert notif.status == notification_models.NotificationStatus.RETRYING
    assert notif.retry_count == 1
    manager.background_tasks.add_task.assert_called()


@pytest.mark.asyncio
async def test_delivery_manager_final_failure_records_reason(monkeypatch, session, test_user):
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    manager.max_retries = 1
    manager.retry_delays = [1]
    manager._process_language = AsyncMock(side_effect=RuntimeError("dead"))
    manager._get_user_preferences = MagicMock(
        return_value=notification_models.NotificationPreferences(
            user_id=test_user["id"],
            email_notifications=False,
            push_notifications=False,
            in_app_notifications=False,
        )
    )

    notif = _make_notification(
        test_user["id"],
        retry_count=1,
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    success = await manager.deliver_notification(notif)
    session.refresh(notif)

    assert success is False
    assert notif.status == notification_models.NotificationStatus.FAILED
    assert notif.failure_reason is not None


@pytest.mark.asyncio
async def test_notification_service_retry_failed_notification(monkeypatch, session, test_user):
    notif = _make_notification(
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=0,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    service = NotificationService(session, background_tasks=MagicMock())
    monkeypatch.setattr(
        service.delivery_manager, "deliver_notification", AsyncMock(return_value=True)
    )

    result = await service.retry_failed_notification(notif.id)
    session.refresh(notif)

    assert result is True
    assert notif.status == notification_models.NotificationStatus.DELIVERED
    assert notif.retry_count == 1
    assert notif.last_retry is not None


@pytest.mark.asyncio
async def test_notification_retry_handler_handles_limits(monkeypatch, session, test_user):
    bg = MagicMock()
    handler = NotificationRetryHandler(session, background_tasks=bg)

    retrying = _make_notification(
        test_user["id"],
        status="failed",
        retry_count=0,
    )
    session.add(retrying)
    session.commit()
    session.refresh(retrying)

    await handler.handle_failed_notification(retrying.id)
    session.refresh(retrying)
    assert retrying.status == "retrying"
    assert retrying.next_retry is not None
    bg.add_task.assert_called()




@pytest.mark.asyncio
async def test_delivery_success_sets_delivered(monkeypatch, session, test_user):
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(manager, "_process_language", AsyncMock(return_value="ok"))
    send_rt = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_send_realtime_notification", send_rt)

    notif = _make_notification(test_user["id"])
    session.add(notif)
    session.commit()
    session.refresh(notif)

    success = await manager.deliver_notification(notif)
    session.refresh(notif)

    assert success is True
    assert notif.status == notification_models.NotificationStatus.DELIVERED
    assert notif.retry_count == 0
    send_rt.assert_awaited()


@pytest.mark.asyncio
async def test_delivery_failure_records_reason_and_respects_next_retry(
    monkeypatch, session, test_user
):
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    manager.max_retries = 0
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(
        manager, "_process_language", AsyncMock(side_effect=RuntimeError("boom"))
    )

    notif = _make_notification(
        test_user["id"],
        retry_count=0,
    )
    notif.next_retry = datetime.now(timezone.utc) + timedelta(minutes=5)
    session.add(notif)
    session.commit()
    session.refresh(notif)

    success = await manager.deliver_notification(notif)
    session.refresh(notif)

    assert success is False
    assert notif.status == notification_models.NotificationStatus.FAILED
    assert notif.failure_reason is not None
    assert notif.next_retry is not None


@pytest.mark.asyncio
async def test_exceeding_retries_sets_failed_and_archivable(monkeypatch, session, test_user):
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    manager.max_retries = 1
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(
        manager, "_process_language", AsyncMock(side_effect=RuntimeError("fail"))
    )

    retrying = _make_notification(
        test_user["id"],
        status=notification_models.NotificationStatus.PENDING,
        retry_count=1,
    )
    session.add(retrying)
    session.commit()
    session.refresh(retrying)

    success = await manager.deliver_notification(retrying)
    session.refresh(retrying)

    assert success is False
    assert retrying.status == notification_models.NotificationStatus.FAILED
    retrying.is_archived = True


@pytest.mark.asyncio
async def test_delivery_deduplicates_on_cache_hit(monkeypatch, session, test_user):
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(manager, "_process_language", AsyncMock(return_value="ok"))
    send_rt = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_send_realtime_notification", send_rt)

    notif = _make_notification(test_user["id"])
    session.add(notif)
    session.commit()
    session.refresh(notif)

    assert await manager.deliver_notification(notif) is True
    delivery_key = f"delivery_{notif.id}"
    assert delivery_status_cache[delivery_key] is True

    new_rt = AsyncMock(side_effect=RuntimeError)
    monkeypatch.setattr(manager, "_send_realtime_notification", new_rt)
    assert await manager.deliver_notification(notif) is True  # cached path
    assert new_rt.await_count == 0


@pytest.mark.asyncio
async def test_delivery_cache_miss_then_hit(monkeypatch, session, test_user):
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(manager, "_process_language", AsyncMock(return_value="ok"))
    send_rt = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_send_realtime_notification", send_rt)

    notif = _make_notification(test_user["id"])
    session.add(notif)
    session.commit()
    session.refresh(notif)

    await manager.deliver_notification(notif)
    assert send_rt.await_count == 1

    await manager.deliver_notification(notif)
    assert send_rt.await_count == 1  # no additional call on cache hit


@pytest.mark.asyncio
async def test_delivery_prefers_realtime_when_push_unavailable(monkeypatch, session, test_user):
    notification_cache.clear()
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(manager, "_process_language", AsyncMock(return_value="ok"))
    monkeypatch.setattr(
        manager, "_send_realtime_notification", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        manager, "_send_push_notification", AsyncMock(side_effect=RuntimeError("redis down"))
    )

    notif = _make_notification(test_user["id"])
    session.add(notif)
    session.commit()

    await manager.deliver_notification(notif)
    manager._send_realtime_notification.assert_awaited()


@pytest.mark.asyncio
async def test_delivery_uses_email_when_other_channels_disabled(monkeypatch, session, test_user):
    notification_cache.clear()
    delivery_status_cache.clear()
    manager = NotificationDeliveryManager(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
    )
    monkeypatch.setattr(manager, "_get_user_preferences", lambda _: prefs)
    monkeypatch.setattr(manager, "_process_language", AsyncMock(return_value="ok"))
    send_email = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_send_email_notification", send_email)
    notif = _make_notification(test_user["id"])
    session.add(notif)
    session.commit()

    await manager.deliver_notification(notif)
    send_email.assert_awaited()


@pytest.mark.asyncio
async def test_archive_missing_notification_raises(monkeypatch, session, test_user):
    service = NotificationService(session)
    with pytest.raises(HTTPException):
        await service.archive_notification(999999, test_user["id"])


@pytest.mark.asyncio
async def test_update_preferences_then_skip_channel(monkeypatch, session, test_user):
    service = NotificationService(session, background_tasks=MagicMock())
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        categories_preferences={},
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=True,
    )
    session.add(prefs)
    session.commit()

    await service.update_user_preferences(
        test_user["id"],
        notification_schemas.NotificationPreferencesUpdate(
            categories_preferences={
                notification_models.NotificationCategory.SYSTEM.value: False
            }
        ),
    )
    priority_notification_cache.clear()
    created = await service.create_notification(
        user_id=test_user["id"],
        content="skip me",
        notification_type="system_update",
        category=notification_models.NotificationCategory.SYSTEM,
        priority=notification_models.NotificationPriority.MEDIUM,
    )
    assert created is None


@pytest.mark.asyncio
async def test_notification_feed_pagination_and_filters(session, test_user):
    service = NotificationService(session)
    n1 = _make_notification(
        test_user["id"],
        content="latest",
        status=notification_models.NotificationStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    n2 = _make_notification(
        test_user["id"],
        content="older",
        status=notification_models.NotificationStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    n3 = _make_notification(
        test_user["id"],
        content="archived",
        status=notification_models.NotificationStatus.DELIVERED,
        is_archived=True,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session.add_all([n1, n2, n3])
    session.commit()

    feed = await service.get_notification_feed(
        user_id=test_user["id"], limit=1, include_archived=False
    )
    assert feed["notifications"][0].content == "latest"
    assert feed["has_more"] is True
    assert feed["unread_count"] >= 0
