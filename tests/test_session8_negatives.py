import pytest

from app import models
from app.modules.notifications.repository import NotificationRepository
from app.services.posts import PostService
from app.routers import search as search_router
from tests.test_session7_routers import make_client


class _StubRedisBad:
    def __init__(self):
        self.store = {}
        self.get_calls = 0

    def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def test_search_ignores_invalid_cache_payload(session, authorized_client, test_user, monkeypatch):
    # seed a post to be found
    post = models.Post(title="Cached Hit", content="body", owner_id=test_user["id"])
    session.add(post)
    session.commit()

    stub = _StubRedisBad()
    cache_key = "search:Cached Hit:relevance"
    stub.store[cache_key] = "not-json"
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setattr(search_router.settings.__class__, "redis_client", stub, raising=False)
    monkeypatch.setattr(search_router, "_cache_client", lambda: stub)

    resp = authorized_client.post("/search/", json={"query": "Cached Hit", "sort_by": "relevance"})
    assert resp.status_code == 200
    assert resp.json()["results"], "Should recompute when cache payload is invalid"


def test_notification_repository_negative_paths(session):
    user = models.User(email="notif@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()

    repo = NotificationRepository(session)
    notification = repo.create_notification(
        user_id=user.id,
        content="n1",
        notification_type=models.NotificationType.SYSTEM_UPDATE.value,
        category=models.NotificationCategory.SYSTEM,
    )
    assert repo.mark_notification_as_read(notification.id, user_id=999) is None
    assert not notification.is_read

    assert repo.soft_delete_notification(999, user_id=1) is None
    assert repo.mark_all_as_read(user_id=2) == 0


@pytest.mark.asyncio
async def test_post_translation_typeerror_skipped(session, test_user, monkeypatch):
    service = PostService(session)
    user = session.get(models.User, test_user["id"])
    post = models.Post(title="Hola", content="Mundo", owner_id=user.id)
    session.add(post)
    session.commit()

    async def bad_translator(content, current_user, lang):
        raise TypeError("bad translator")

    posts = await service.list_posts(
        current_user=user,
        limit=5,
        skip=0,
        search="Hola",
        translate=True,
        translator_fn=bad_translator,
    )
    assert posts and posts[0].content == "Mundo"


def test_screen_share_end_not_found(session):
    user = models.User(email="screen@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()

    with make_client(session, current_user=user) as client:
        resp = client.post("/screen-share/end", json={"session_id": 999})
        assert resp.status_code == 404
