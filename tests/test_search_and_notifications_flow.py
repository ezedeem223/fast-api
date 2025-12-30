import json

from app import models
from app.core.config import settings
from app.modules.notifications import models as notification_models
from app.modules.users.schemas import SortOption
from app.routers import search as search_router


class _StubRedis:
    def __init__(self):
        self.store = {}
        self.setex_calls = []
        self.get_calls = []
        self.deleted = []

    def get(self, key):
        self.get_calls.append(key)
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value

    def scan_iter(self, match=None):
        pattern = match or "*"
        for key in list(self.store.keys()):
            if not pattern or key.startswith(pattern.rstrip("*")) or pattern == "*":
                yield key

    def delete(self, *keys):
        for key in keys:
            self.deleted.append(key)
            self.store.pop(key, None)


def test_search_uses_cache_and_returns_cached_payload(
    authorized_client, session, test_post, monkeypatch
):
    stub = _StubRedis()
    # enable cache path and force stub redis client
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setattr(settings.__class__, "redis_client", stub, raising=False)
    monkeypatch.setattr(search_router, "_cache_client", lambda: stub)

    first = authorized_client.post(
        "/search/", json={"query": "Fixture", "sort_by": "relevance"}
    )
    assert first.status_code == 200
    cache_key = f"search:Fixture:{SortOption.RELEVANCE}"
    # Seed cache manually to simulate a stored payload for the follow-up request.
    stub.store[cache_key] = json.dumps(first.json())

    # wipe posts to ensure second call is served from cache (no DB hits needed)
    session.query(models.Post).delete()
    session.commit()

    second = authorized_client.post(
        "/search/", json={"query": "Fixture", "sort_by": "relevance"}
    )
    assert second.status_code == 200
    assert stub.get_calls, "cache should be read on subsequent search"
    assert second.json() == first.json()


def test_notification_feed_mark_read_and_mark_all(
    authorized_client, session, test_user, test_user2
):
    # create notifications for current user
    items = [
        notification_models.Notification(
            user_id=test_user["id"],
            content=f"n{i}",
            notification_type=notification_models.NotificationType.SYSTEM_UPDATE.value,
            category=notification_models.NotificationCategory.SYSTEM,
            priority=notification_models.NotificationPriority.MEDIUM,
        )
        for i in range(3)
    ]
    other_user = notification_models.Notification(
        user_id=test_user2["id"],
        content="ignore-other-user",
        category=notification_models.NotificationCategory.SOCIAL,
    )
    session.add_all(items + [other_user])
    session.commit()

    feed_res = authorized_client.get("/notifications/feed?limit=2&mark_read=true")
    assert feed_res.status_code == 200
    feed = feed_res.json()
    returned_ids = [n["id"] for n in feed["notifications"]]
    # fetched items should be marked as read
    fetched = (
        session.query(notification_models.Notification)
        .filter(notification_models.Notification.id.in_(returned_ids))
        .all()
    )
    assert fetched and all(n.is_read for n in fetched)
    # only one unread left for the current user
    remaining_unread = (
        session.query(notification_models.Notification)
        .filter(
            notification_models.Notification.user_id == test_user["id"],
            notification_models.Notification.is_read.is_(False),
            notification_models.Notification.is_deleted.is_(False),
        )
        .count()
    )
    assert remaining_unread == 1

    mark_all = authorized_client.put("/notifications/mark-all-read")
    assert mark_all.status_code == 200
    remaining_unread_after = (
        session.query(notification_models.Notification)
        .filter(
            notification_models.Notification.user_id == test_user["id"],
            notification_models.Notification.is_read.is_(False),
            notification_models.Notification.is_deleted.is_(False),
        )
        .count()
    )
    assert remaining_unread_after == 0
