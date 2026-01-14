"""Additional coverage for notifications router endpoints."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from tests.testclient import TestClient

from app.routers import notifications as notifications_router


def _make_client(current_user, db=None):
    app = FastAPI()
    app.include_router(notifications_router.router)

    def override_db():
        yield db or object()

    app.dependency_overrides[notifications_router.get_db] = override_db
    app.dependency_overrides[
        notifications_router.oauth2.get_current_user
    ] = lambda: current_user
    return TestClient(app)


def _prefs_payload(user_id, *, email=True):
    now = datetime.now(timezone.utc)
    return {
        "id": 1,
        "user_id": user_id,
        "email_notifications": email,
        "push_notifications": True,
        "in_app_notifications": True,
        "quiet_hours_start": None,
        "quiet_hours_end": None,
        "categories_preferences": {},
        "notification_frequency": "instant",
        "created_at": now,
        "updated_at": None,
    }


def _notification_out(notification_id=1):
    now = datetime.now(timezone.utc)
    return {
        "id": notification_id,
        "content": "hello",
        "notification_type": "system",
        "priority": "normal",
        "category": "info",
        "link": None,
        "is_read": False,
        "is_archived": False,
        "read_at": None,
        "created_at": now,
        "group": None,
        "metadata": {},
    }


def _group_out(group_id=1):
    now = datetime.now(timezone.utc)
    return {
        "id": group_id,
        "group_type": "system",
        "count": 2,
        "last_updated": now,
        "sample_notification": _notification_out(),
    }


def test_notification_mutations_invalidate_cache(monkeypatch):
    """Mark/read/delete/archive/bulk endpoints invalidate caches."""

    class DummyService:
        def __init__(self, db):
            self.db = db

        async def mark_as_read(self, notification_id, user_id):
            return {"id": notification_id, "is_read": True}

        async def mark_all_as_read(self, user_id):
            return {"count": 2}

        async def delete_notification(self, notification_id, user_id):
            return {"deleted": notification_id}

        async def archive_notification(self, notification_id, user_id):
            return {"archived": notification_id}

        async def clear_all_read(self, user_id):
            return {"cleared": 1}

        async def bulk_mark_as_read(self, notification_ids, user_id):
            return {"updated": len(notification_ids)}

        async def bulk_delete(self, notification_ids, user_id):
            return {"deleted": len(notification_ids)}

    monkeypatch.setattr(notifications_router, "NotificationService", DummyService)
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(notifications_router.cache_manager, "invalidate", invalidate_mock)

    user = SimpleNamespace(id=10, is_admin=False)
    client = _make_client(user)

    assert client.put("/notifications/1/read").status_code == 200
    assert client.put("/notifications/mark-all-read").status_code == 200
    assert client.delete("/notifications/1").status_code == 200
    assert client.put("/notifications/1/archive").status_code == 200
    clear_all_result = asyncio.run(
        notifications_router.clear_all_notifications(
            request=SimpleNamespace(),
            db=object(),
            current_user=user,
        )
    )
    assert clear_all_result is not None
    assert client.put("/notifications/bulk-mark-read", json=[1, 2]).status_code == 200
    bulk_delete_result = asyncio.run(
        notifications_router.bulk_delete_notifications(
            request=SimpleNamespace(),
            notification_ids=[1, 2],
            db=object(),
            current_user=user,
        )
    )
    assert bulk_delete_result is not None

    assert invalidate_mock.await_count == 7
    for call in invalidate_mock.await_args_list:
        assert f"notifications:*u{user.id}*" in call.args[0]


def test_notification_preferences_unread_and_groups(monkeypatch):
    """Unread count, preferences, and group endpoints return expected payloads."""
    prefs = _prefs_payload(user_id=11)
    group = _group_out(group_id=3)

    class DummyService:
        def __init__(self, db):
            self.db = db

        async def get_unread_count(self, user_id):
            return 5

        async def get_preferences(self, user_id):
            return prefs

        async def update_preferences(self, user_id, preferences):
            updated = dict(prefs)
            updated["email_notifications"] = preferences.email_notifications
            return updated

        async def get_notification_groups(self, user_id, skip, limit):
            return [group]

        async def expand_group(self, group_id, user_id):
            return group

    monkeypatch.setattr(notifications_router, "NotificationService", DummyService)
    user = SimpleNamespace(id=11, is_admin=False)
    client = _make_client(user)

    unread = client.get("/notifications/unread-count")
    assert unread.status_code == 200
    assert unread.json()["unread_count"] == 5

    prefs_resp = client.get("/notifications/preferences")
    assert prefs_resp.status_code == 200
    assert prefs_resp.json()["user_id"] == user.id

    updated = client.put(
        "/notifications/preferences", json={"email_notifications": False}
    )
    assert updated.status_code == 200
    assert updated.json()["email_notifications"] is False

    groups = client.get("/notifications/groups")
    assert groups.status_code == 200
    assert groups.json()[0]["id"] == group["id"]

    expand = client.put("/notifications/groups/3/expand")
    assert expand.status_code == 200
    assert expand.json()["id"] == group["id"]


def test_send_bulk_requires_admin(monkeypatch):
    """Non-admin bulk send is rejected."""
    user = SimpleNamespace(id=12, is_admin=False)
    client = _make_client(user)
    resp = client.post(
        "/notifications/send-bulk",
        json={"user_ids": [1], "content": "hi"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_notifications_admin_schedule_devices_and_analytics(monkeypatch):
    """Admin and ancillary endpoints hit manager/analytics/service paths."""

    class DummyService:
        def __init__(self, db):
            self.db = db

        async def get_scheduled_notifications(self, user_id, skip, limit):
            return []

        async def cancel_scheduled_notification(self, notification_id, user_id):
            return {"cancelled": notification_id}

        async def register_device_token(self, user_id, device_token, device_type):
            return {"device_token": device_token, "device_type": device_type}

        async def unregister_device_token(self, user_id, device_token):
            return {"device_token": device_token, "status": "removed"}

    class DummyManager:
        def __init__(self, db):
            self.db = db

        async def send_bulk_notifications(
            self,
            user_ids,
            content,
            notification_type,
            category,
            priority,
            background_tasks,
        ):
            return {"sent": len(user_ids)}

        async def schedule_notification(
            self,
            user_id,
            content,
            scheduled_for,
            notification_type,
            category,
            priority,
            background_tasks,
        ):
            return {"scheduled_for": scheduled_for.isoformat()}

        async def send_test_notification(self, user_id, background_tasks):
            return {"status": "ok"}

        async def retry_failed_notifications(self, background_tasks):
            return {"retried": 2}

    class DummyAnalytics:
        def __init__(self, db):
            self.db = db

        async def get_user_analytics(self, user_id, days):
            return {
                "engagement_rate": 0.5,
                "response_time": 2.0,
                "peak_activity_hours": [{"hour": 1, "count": 2}],
                "most_interacted_types": [{"type": "system", "count": 3}],
            }

        async def get_delivery_stats(self, user_id, days):
            return {"delivered": 1}

        async def get_engagement_metrics(self, user_id, days):
            return {"clicks": 4}

        async def get_system_stats(self, days):
            return {"total": 10}

        async def get_delivery_logs(self, skip, limit, status):
            return []

    monkeypatch.setattr(notifications_router, "NotificationService", DummyService)
    monkeypatch.setattr(notifications_router, "NotificationManager", DummyManager)
    monkeypatch.setattr(
        notifications_router, "NotificationAnalyticsService", DummyAnalytics
    )

    admin = SimpleNamespace(id=13, is_admin=True)
    client = _make_client(admin)

    bulk = client.post(
        "/notifications/send-bulk",
        json={"user_ids": [1, 2], "content": "hi"},
    )
    assert bulk.status_code == 200
    assert bulk.json()["sent"] == 2

    scheduled_for = datetime.now(timezone.utc).isoformat()
    schedule = client.post(
        "/notifications/schedule",
        json={"user_id": 1, "content": "later", "scheduled_for": scheduled_for},
    )
    assert schedule.status_code == 200

    scheduled = client.get("/notifications/scheduled")
    assert scheduled.status_code == 200
    assert scheduled.json() == []

    cancel = client.delete("/notifications/scheduled/5")
    assert cancel.status_code == 200

    register = client.post(
        "/notifications/register-device",
        json={"device_token": "tok", "device_type": "web"},
    )
    assert register.status_code == 200

    unregister_result = asyncio.run(
        notifications_router.unregister_device_token(
            request=SimpleNamespace(),
            device_token="tok",
            db=object(),
            current_user=admin,
        )
    )
    assert unregister_result is not None

    test_push = client.post("/notifications/test-push")
    assert test_push.status_code == 200

    analytics = client.get("/notifications/analytics")
    assert analytics.status_code == 200

    delivery = client.get("/notifications/analytics/delivery-stats")
    assert delivery.status_code == 200

    engagement = client.get("/notifications/analytics/engagement")
    assert engagement.status_code == 200

    admin_stats = client.get("/notifications/admin/stats")
    assert admin_stats.status_code == 200

    retry = client.post("/notifications/admin/retry-failed")
    assert retry.status_code == 200

    logs = client.get("/notifications/admin/delivery-logs")
    assert logs.status_code == 200
    assert logs.json() == []
