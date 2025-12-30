from datetime import datetime, timedelta

from app import models
from app.modules.search.typesense_client import TypesenseClient
from app.routers import search as search_router
from tests.conftest import TestingSessionLocal


class _StubCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def _make_post(
    owner_id: int, title: str, content: str, created_at: datetime | None = None
) -> int:
    with TestingSessionLocal() as db:
        owner = db.get(models.User, owner_id)
        post = models.Post(
            owner_id=owner_id,
            title=title,
            content=content,
            is_safe_content=True,
            created_at=created_at or (datetime.now() - timedelta(minutes=1)),
        )
        if owner is not None:
            post.owner = owner
        db.add(post)
        db.commit()
        db.refresh(post)
        return post.id


def test_search_uses_cache_and_skips_record(monkeypatch, authorized_client, test_user):
    stub_cache = _StubCache()
    monkeypatch.setattr(search_router, "_cache_client", lambda: stub_cache)

    called = {"count": 0}

    def _record(db, query, user_id):
        called["count"] += 1

    monkeypatch.setattr(search_router, "record_search_query", _record)

    _make_post(test_user["id"], "hello", "hello world")
    resp1 = authorized_client.post(
        "/search/", json={"query": "hello", "sort_by": "date_desc"}
    )
    assert resp1.status_code == 200
    assert called["count"] == 1
    resp2 = authorized_client.post(
        "/search/", json={"query": "hello", "sort_by": "date_desc"}
    )
    assert resp2.status_code == 200
    assert called["count"] == 1  # cache hit, record not called again
    assert resp2.json()["results"][0]["id"] == resp1.json()["results"][0]["id"]


def test_typesense_ordering(monkeypatch, authorized_client, test_user):
    first_id = _make_post(test_user["id"], "First", "alpha")
    second_id = _make_post(test_user["id"], "Second", "beta")

    class FakeTypesense(TypesenseClient):
        def __init__(self):
            pass

        def search_posts(self, query: str, limit: int = 10):
            return [
                {"document": {"post_id": second_id}},
                {"document": {"post_id": first_id}},
            ]

    monkeypatch.setattr(search_router, "get_typesense_client", lambda: FakeTypesense())

    resp = authorized_client.post(
        "/search/", json={"query": "a", "sort_by": "relevance"}
    )
    assert resp.status_code == 200
    ids = [post["id"] for post in resp.json()["results"]]
    assert ids[:2] == [second_id, first_id]


def test_advanced_search_filters_by_author_and_date(
    authorized_client, test_user, test_user2
):
    # make posts for two users, only one should match
    matched_id = _make_post(test_user2["id"], "Match", "recent")
    _make_post(
        test_user2["id"],
        "Old",
        "old content",
        created_at=datetime.now() - timedelta(days=2),
    )
    other_id = _make_post(test_user["id"], "Other", "other")

    start = datetime.now() - timedelta(hours=1)
    resp = authorized_client.get(
        "/search/advanced",
        params={
            "query": "rec",
            "author_id": test_user2["id"],
            "start_date": start.isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = [post["id"] for post in body["posts"]]
    assert matched_id in ids
    assert other_id not in ids
