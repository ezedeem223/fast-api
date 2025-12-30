import asyncio

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.notifications import models as notification_models
from app.modules.notifications.common import get_model_by_id, handle_async_errors
from app.modules.notifications.repository import NotificationRepository

# ============== 21) repository.get_model_by_id ==============


def test_get_model_by_id_returns_model(session):
    repo = NotificationRepository(session)
    n = repo.create_notification(
        user_id=1,
        content="hello",
        notification_type="t",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        notification_metadata={},
    )
    found = get_model_by_id(session, notification_models.Notification, n.id)
    assert found is not None
    assert found.id == n.id


def test_get_model_by_id_missing_returns_none(session):
    found = get_model_by_id(session, notification_models.Notification, 99999)
    assert found is None


def test_get_model_by_id_safe_with_bad_type(session):
    # passing a non-int should not raise, just return None
    found = get_model_by_id(session, notification_models.Notification, "bad-id")  # type: ignore[arg-type]
    assert found is None


# ============== 22) repository.cleanup_archived ==============


def test_cleanup_archived_removes_read_before_cutoff(session):
    repo = NotificationRepository(session)
    n = repo.create_notification(
        user_id=1,
        content="archived",
        notification_type="t",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        notification_metadata={},
    )
    n.is_archived = True
    session.commit()
    removed = repo.cleanup_archived(n.created_at)
    assert removed >= 1


def test_cleanup_archived_no_data_is_noop(session):
    repo = NotificationRepository(session)
    removed = repo.cleanup_archived(
        notification_models.Notification.created_at
    )  # arbitrary cutoff
    assert removed == 0


def test_cleanup_archived_rolls_back_on_error(monkeypatch, session):
    repo = NotificationRepository(session)
    rollback_flag = {"rolled": False}
    orig_rollback = session.rollback

    def boom():
        raise SQLAlchemyError("db fail")

    def fake_rollback():
        rollback_flag["rolled"] = True
        return orig_rollback()

    monkeypatch.setattr(session, "commit", boom)
    monkeypatch.setattr(session, "rollback", fake_rollback)

    with pytest.raises(SQLAlchemyError):
        repo.cleanup_archived(notification_models.Notification.created_at)
    assert rollback_flag["rolled"] is True


# ============== 23) common.handle_async_errors ==============


def test_handle_async_errors_success_path():
    @handle_async_errors
    async def ok_fn():
        return "ok"

    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(ok_fn())
    loop.close()
    assert result == "ok"


def test_handle_async_errors_catches_exception(caplog):
    @handle_async_errors
    async def bad_fn():
        raise RuntimeError("boom")

    caplog.set_level("ERROR")
    loop = asyncio.new_event_loop()
    with pytest.raises(RuntimeError):
        loop.run_until_complete(bad_fn())
    loop.close()
    assert any("boom" in rec.message for rec in caplog.records)
