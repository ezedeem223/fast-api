import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.notifications import models as notification_models
from app.modules.notifications.common import delivery_status_cache
from app.modules.notifications.service import NotificationDeliveryManager


@pytest.fixture(autouse=True)
def _clear_caches():
    # Ensure per-test isolation so retry paths are not affected by prior runs.
    delivery_status_cache.clear()
    yield
    delivery_status_cache.clear()


def _make_delivery_manager(session, *, with_tasks=False):
    mgr = NotificationDeliveryManager(
        session, background_tasks=MagicMock() if with_tasks else None
    )
    mgr._process_language = AsyncMock(side_effect=lambda content, *_: content)  # type: ignore[attr-defined]
    return mgr


def _notification(
    session,
    user_id,
    status=notification_models.NotificationStatus.PENDING,
    retry_count=0,
):
    n = notification_models.Notification(
        user_id=user_id,
        content="payload",
        notification_type="test",
        status=status,
        retry_count=retry_count,
    )
    n.language = "en"  # used by delivery flow
    session.add(n)
    session.commit()
    session.refresh(n)
    return n


@pytest.mark.asyncio
async def test_max_retries_exhausted_sets_failed_and_reason(session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=mgr.max_retries,
    )

    # simulate error path to trigger _handle_final_failure via exception
    mgr._process_language = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    session.refresh(n)
    assert success is False
    assert n.status == notification_models.NotificationStatus.FAILED
    assert n.failure_reason is not None
    assert "boom" in json.loads(n.failure_reason)["error_message"]
    assert n.retry_count == mgr.max_retries


@pytest.mark.asyncio
async def test_schedule_retry_not_added_when_background_tasks_absent(
    session, test_user, monkeypatch
):
    mgr = _make_delivery_manager(session, with_tasks=False)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=0,
    )

    # force exception before delivery tasks to enter retry path
    mgr._process_language = AsyncMock(side_effect=RuntimeError("fail"))  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.RETRYING
    # no background_tasks so nothing enqueued, retry_count increased
    assert n.retry_count == 1
    assert n.next_retry is not None
    assert mgr.error_tracking.get(n.id) is not None


@pytest.mark.asyncio
async def test_background_tasks_added_when_present(session, test_user, monkeypatch):
    bg = MagicMock()
    mgr = NotificationDeliveryManager(session, background_tasks=bg)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._process_language = AsyncMock(side_effect=lambda content, *_: content)  # type: ignore[attr-defined]
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=0,
    )

    mgr._process_language = AsyncMock(side_effect=RuntimeError("fail"))  # type: ignore[attr-defined]

    await mgr.deliver_notification(n)
    # background task should be added for retry_delivery
    assert bg.add_task.called


@pytest.mark.asyncio
async def test_delivery_status_cache_cleared_on_failure(
    session, test_user, monkeypatch
):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(session, test_user["id"])
    mgr._process_language = AsyncMock(side_effect=RuntimeError("fail"))  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    assert success is False
    key = f"delivery_{n.id}"
    assert key in delivery_status_cache  # updated إلى failure
    assert delivery_status_cache[key] is False


@pytest.mark.asyncio
async def test_no_channels_keeps_status_pending_and_no_retry(session, test_user):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.PENDING,
        retry_count=0,
    )

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.PENDING
    assert n.retry_count == 0


@pytest.mark.asyncio
async def test_no_new_retry_when_max_retries_reached(session, test_user):
    bg = MagicMock()
    mgr = NotificationDeliveryManager(session, background_tasks=bg)
    prefs = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=mgr.max_retries - 1,
    )
    mgr._process_language = AsyncMock(side_effect=RuntimeError("fatal"))  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.FAILED
    assert n.failure_reason is not None
    assert n.retry_count == mgr.max_retries - 1  # no increment beyond max
    assert not bg.add_task.called


@pytest.mark.asyncio
async def test_update_delivery_status_exception_triggers_rollback(
    monkeypatch, session, test_user
):
    mgr = _make_delivery_manager(session)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(session, test_user["id"])
    commit_flag = {"rolled_back": False}

    async def raise_in_update(notification, success, results):
        raise RuntimeError("commit fail")

    orig_rollback = session.rollback

    def fake_rollback():
        commit_flag["rolled_back"] = True
        return orig_rollback()

    monkeypatch.setattr(mgr, "_update_delivery_status", raise_in_update)
    monkeypatch.setattr(session, "rollback", fake_rollback)
    mgr._process_language = AsyncMock(side_effect=lambda c, *_: c)  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    assert success is False
    assert commit_flag["rolled_back"] is True
    session.refresh(n)
    assert n.status in (
        notification_models.NotificationStatus.RETRYING,
        notification_models.NotificationStatus.FAILED,
    )


@pytest.mark.asyncio
async def test_retry_count_one_behaves_like_zero(session, test_user):
    mgr = _make_delivery_manager(session, with_tasks=False)
    prefs = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.FAILED,
        retry_count=1,
    )
    n.notification_metadata = {"keep": "me"}
    mgr._process_language = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]

    success = await mgr.deliver_notification(n)
    assert success is False
    session.refresh(n)
    assert n.status == notification_models.NotificationStatus.RETRYING
    assert n.retry_count == 2
    assert mgr.error_tracking.get(n.id) is not None
    assert n.notification_metadata == {"keep": "me"}
