"""Test module for test notifications service session17."""
from types import SimpleNamespace

import pytest

from app.modules.notifications import service as notif_service
from app.modules.notifications.common import delivery_status_cache


class DummyDB:
    """Test class for DummyDB."""
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def make_notification(**kwargs):
    """Helper for make notification."""
    defaults = {
        "id": 1,
        "user_id": 10,
        "content": "hello",
        "language": "en",
        "notification_type": "info",
        "retry_count": 0,
        "notification_metadata": {},
        "status": notif_service.notification_models.NotificationStatus.PENDING,
        "failure_reason": None,
        "is_deleted": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_deliver_notification_no_channels(monkeypatch):
    """Test case for test deliver notification no channels."""
    db = DummyDB()
    manager = notif_service.NotificationDeliveryManager(db)

    # No channels enabled
    prefs = SimpleNamespace(
        email_notifications=False, push_notifications=False, in_app_notifications=False
    )
    manager._get_user_preferences = lambda user_id: prefs  # type: ignore[assignment]

    async def proc(content, lang, prefs):
        return content

    manager._process_language = proc  # type: ignore[assignment]
    manager._send_email_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._send_push_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._send_realtime_notification = lambda *a, **k: None  # type: ignore[assignment]

    notification = make_notification()
    delivery_status_cache.clear()
    result = await manager.deliver_notification(notification)
    assert result is False
    assert db.commits == 1  # committed after deciding no channels


@pytest.mark.asyncio
async def test_deliver_notification_email_only(monkeypatch):
    """Test case for test deliver notification email only."""
    db = DummyDB()
    manager = notif_service.NotificationDeliveryManager(db)

    prefs = SimpleNamespace(
        email_notifications=True, push_notifications=False, in_app_notifications=False
    )
    manager._get_user_preferences = lambda user_id: prefs  # type: ignore[assignment]

    async def proc(content, lang, prefs):
        return content

    manager._process_language = proc  # type: ignore[assignment]

    calls = {"email": 0}

    async def fake_email(notification, content):
        calls["email"] += 1
        return True

    async def fake_update(notification, success, results):
        calls["updated"] = (success, results)

    manager._send_email_notification = fake_email  # type: ignore[assignment]
    manager._send_push_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._send_realtime_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._update_delivery_status = fake_update  # type: ignore[assignment]

    notification = make_notification()
    delivery_status_cache.clear()
    result = await manager.deliver_notification(notification)
    assert result is True
    assert calls["email"] == 1
    assert calls["updated"][0] is True
    assert db.commits == 0  # commit handled in update hook if desired


@pytest.mark.asyncio
async def test_deliver_notification_retry_and_failure(monkeypatch):
    """Test case for test deliver notification retry and failure."""
    db = DummyDB()
    manager = notif_service.NotificationDeliveryManager(db)
    manager.max_retries = 1

    prefs = SimpleNamespace(
        email_notifications=True, push_notifications=False, in_app_notifications=False
    )
    manager._get_user_preferences = lambda user_id: prefs  # type: ignore[assignment]

    async def proc(content, lang, prefs):
        return content

    manager._process_language = proc  # type: ignore[assignment]

    async def boom_email(notification, content):
        raise RuntimeError("fail")

    retried = {"count": 0}
    final_failure = {"called": False}

    async def fake_schedule_retry(notification):
        retried["count"] += 1

    async def fake_handle_final_failure(notification, error_details):
        final_failure["called"] = True

    manager._send_email_notification = boom_email  # type: ignore[assignment]
    manager._send_push_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._send_realtime_notification = lambda *a, **k: None  # type: ignore[assignment]
    manager._schedule_retry = fake_schedule_retry  # type: ignore[assignment]
    manager._handle_final_failure = fake_handle_final_failure  # type: ignore[assignment]

    notification = make_notification(retry_count=0)
    delivery_status_cache.clear()
    result = await manager.deliver_notification(notification)
    assert result is False
    assert retried["count"] == 0  # with max_retries=1 should call final failure
    assert final_failure["called"] is True
    assert delivery_status_cache[f"delivery_{notification.id}"] is False
