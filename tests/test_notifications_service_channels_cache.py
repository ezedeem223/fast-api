from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.notifications import models as notification_models
from app.modules.notifications.common import delivery_status_cache
from app.modules.notifications.service import NotificationDeliveryManager
from app.modules.notifications import service as notifications_service


@pytest.fixture(autouse=True)
def _clear_delivery_cache():
    delivery_status_cache.clear()
    yield
    delivery_status_cache.clear()


def _make_delivery_manager(session):
    mgr = NotificationDeliveryManager(session)
    mgr._process_language = AsyncMock(side_effect=lambda content, *_: content)  # type: ignore[attr-defined]
    return mgr


def _make_notification(session, user_id):
    notif = notification_models.Notification(
        user_id=user_id,
        content="payload",
        notification_type="test",
        status=notification_models.NotificationStatus.PENDING,
    )
    notif.language = "en"
    session.add(notif)
    session.commit()
    session.refresh(notif)
    return notif


# ===================== 11) delivery_status_cache hits =====================


@pytest.mark.asyncio
async def test_delivery_cache_hit_returns_without_sending(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    key = f"delivery_{n.id}"
    delivery_status_cache[key] = True

    email_mock = AsyncMock(side_effect=AssertionError("should not send"))
    monkeypatch.setattr(mgr, "_send_email_notification", email_mock)

    success = await mgr.deliver_notification(n)
    assert success is True
    assert email_mock.await_count == 0
    session.refresh(n)
    # status unchanged because we returned early
    assert n.status == notification_models.NotificationStatus.PENDING


@pytest.mark.asyncio
async def test_delivery_cache_cleared_triggers_send_and_sets_success(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    key = f"delivery_{n.id}"
    delivery_status_cache[key] = True
    delivery_status_cache.pop(key)

    email_mock = AsyncMock()
    monkeypatch.setattr(mgr, "_send_email_notification", email_mock)

    success = await mgr.deliver_notification(n)
    assert success is True
    email_mock.assert_awaited_once()
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED
    assert delivery_status_cache.get(key) is True


@pytest.mark.asyncio
async def test_delivery_cache_updates_to_failure_on_send_error(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    key = f"delivery_{n.id}"
    delivery_status_cache.pop(key, None)

    email_mock = AsyncMock(side_effect=RuntimeError("smtp down"))
    monkeypatch.setattr(mgr, "_send_email_notification", email_mock)

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.FAILED
    assert delivery_status_cache.get(key) is False


# ===================== 12) push channel =====================


@pytest.mark.asyncio
async def test_push_channel_success_sets_delivered(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    push_mock = AsyncMock()
    monkeypatch.setattr(mgr, "_send_push_notification", push_mock)

    success = await mgr.deliver_notification(n)
    assert success is True
    push_mock.assert_awaited_once()
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED
    log = session.query(notification_models.NotificationDeliveryLog).filter_by(notification_id=n.id).first()
    assert log is not None
    assert log.delivery_channel == "all"


@pytest.mark.asyncio
async def test_push_channel_exception_logged_and_marks_failed(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def fail_push(*_, **__):
        raise RuntimeError("push error")

    monkeypatch.setattr(mgr, "_send_push_notification", fail_push)
    caplog.set_level("ERROR")

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.FAILED
    key = f"delivery_{n.id}"
    assert delivery_status_cache.get(key) is False


@pytest.mark.asyncio
async def test_push_channel_no_devices_returns_without_error(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def no_devices(notification, content):
        notifications_service.logger.info("No active devices for user %s", notification.user_id)
        return None

    monkeypatch.setattr(mgr, "_send_push_notification", no_devices)
    caplog.set_level("INFO")

    success = await mgr.deliver_notification(n)
    assert success is True
    assert any("No active devices" in rec.message for rec in caplog.records)
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_push_channel_status_and_log_consistent(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())

    success = await mgr.deliver_notification(n)
    assert success is True
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED
    log = session.query(notification_models.NotificationDeliveryLog).filter_by(notification_id=n.id).first()
    assert log is not None
    assert log.status == notification_models.NotificationStatus.DELIVERED.value


# ===================== 13) email channel =====================


@pytest.mark.asyncio
async def test_email_channel_missing_email_logs_warning(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def warn_email(notification, content):
        notifications_service.logger.warning("No email found for user %s", notification.user_id)

    monkeypatch.setattr(mgr, "_send_email_notification", warn_email)
    caplog.set_level("WARNING")

    success = await mgr.deliver_notification(n)
    assert success is True
    assert any("No email found" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_email_channel_timeout_logged(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def timeout_email(*_, **__):
        raise TimeoutError("smtp timeout")

    monkeypatch.setattr(mgr, "_send_email_notification", timeout_email)
    caplog.set_level("ERROR")

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.FAILED


@pytest.mark.asyncio
async def test_email_channel_bad_credentials_logged(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def bad_auth(*_, **__):
        raise RuntimeError("bad auth")

    monkeypatch.setattr(mgr, "_send_email_notification", bad_auth)
    caplog.set_level("ERROR")

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.FAILED


# ===================== 14) realtime channel =====================


@pytest.mark.asyncio
async def test_realtime_channel_success(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    ws_mock = AsyncMock()
    monkeypatch.setattr("app.modules.notifications.service.manager.send_personal_message", ws_mock)

    success = await mgr.deliver_notification(n)
    assert success is True
    ws_mock.assert_awaited_once()
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_realtime_channel_exception_logs(monkeypatch, session, test_user, caplog):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    async def fail_ws(notification, content):
        raise RuntimeError("ws fail")

    monkeypatch.setattr(mgr, "_send_realtime_notification", fail_ws)
    caplog.set_level("ERROR")

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status in (
        notification_models.NotificationStatus.RETRYING,
        notification_models.NotificationStatus.FAILED,
    )
    key = f"delivery_{n.id}"
    assert delivery_status_cache.get(key) is False


@pytest.mark.asyncio
async def test_realtime_channel_accepts_dict_payload(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])
    ws_mock = AsyncMock()
    monkeypatch.setattr("app.modules.notifications.service.manager.send_personal_message", ws_mock)

    success = await mgr.deliver_notification(n)
    assert success is True
    ws_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_email_channel_success_adds_log(monkeypatch, session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _make_notification(session, test_user["id"])

    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())

    success = await mgr.deliver_notification(n)
    assert success is True
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.DELIVERED
    log = session.query(notification_models.NotificationDeliveryLog).filter_by(notification_id=n.id).first()
    assert log is not None
    assert log.status == notification_models.NotificationStatus.DELIVERED.value
