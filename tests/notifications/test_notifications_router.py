"""Test module for test session9 notifications router."""
from unittest.mock import AsyncMock

import pytest

from app import models
from app.modules.notifications import models as notif_models
from app.modules.notifications.service import NotificationService
from app.notifications import create_notification as sync_create_notification
from tests.conftest import TestingSessionLocal


def _make_user(db, email: str):
    """Helper for  make user."""
    user = models.User(email=email, hashed_password="x", is_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_notification_in_app_only(monkeypatch):
    """Test case for test create notification in app only."""
    with TestingSessionLocal() as db:
        user = _make_user(db, "notif@app.com")
        service = NotificationService(db)

        # Disable email/push preferences to ensure in-app still persists
        prefs = notif_models.NotificationPreferences(
            user_id=user.id,
            email_notifications=False,
            push_notifications=False,
            in_app_notifications=True,
        )
        db.add(prefs)
        db.commit()

        delivery_spy = AsyncMock(return_value=True)
        monkeypatch.setattr(
            service.delivery_manager, "deliver_notification", delivery_spy
        )

        notification = await service.create_notification(
            user_id=user.id,
            content="Hello",
            notification_type="system_update",
        )
        assert notification is not None
        delivery_spy.assert_awaited_once()
        persisted = db.get(notif_models.Notification, notification.id)
        assert persisted.notification_type == "system_update"


@pytest.mark.asyncio
async def test_retry_flow_marks_failed(monkeypatch):
    """Test case for test retry flow marks failed."""
    with TestingSessionLocal() as db:
        user = _make_user(db, "retry@app.com")
        service = NotificationService(db)

        async def _fail(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(service.delivery_manager, "_send_email_notification", _fail)
        monkeypatch.setattr(service.delivery_manager, "_send_push_notification", _fail)
        monkeypatch.setattr(
            service.delivery_manager, "_send_realtime_notification", _fail
        )
        # Force prefs to allow all so failure path is exercised without DB-bound prefs
        fake_prefs = notif_models.NotificationPreferences(
            user_id=user.id,
            email_notifications=True,
            push_notifications=True,
            in_app_notifications=True,
            categories_preferences={},
        )
        monkeypatch.setattr(service, "_get_user_preferences", lambda *_: fake_prefs)

        notification = await service.create_notification(
            user_id=user.id,
            content="Fail me",
            notification_type="system_update",
        )
        db.refresh(notification)
        assert notification.status in {
            notif_models.NotificationStatus.FAILED,
            notif_models.NotificationStatus.RETRYING,
        }
        assert notification.retry_count >= 0


def test_sync_create_notification_persists():
    """Test case for test sync create notification persists."""
    with TestingSessionLocal() as db:
        user = _make_user(db, "sync@app.com")
        notif = sync_create_notification(
            db,
            user_id=user.id,
            content="Sync create",
            link="/n/1",
            notification_type="system_update",
        )
        assert notif.id is not None
        fetched = db.get(notif_models.Notification, notif.id)
        assert fetched.link == "/n/1"
