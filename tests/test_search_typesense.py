import os

os.environ["APP_ENV"] = "test"
os.environ["REDIS_URL"] = ""

import pytest

from app import models
from app.routers import search as search_router


class FakeTypesenseClient:
    def __init__(self, hits=None, should_raise=False):
        self.hits = hits or []
        self.should_raise = should_raise
        self.calls = []

    def search_posts(self, query, limit=10):
        self.calls.append((query, limit))
        if self.should_raise:
            raise RuntimeError("typesense error")
        return self.hits


@pytest.fixture
def sample_posts(session, test_user):
    post_ids = []
    for idx in range(2):
        post = models.Post(
            title=f"Hello {idx}",
            content=f"Body {idx}",
            owner_id=test_user["id"],
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        post_ids.append(post.id)
    return post_ids


@pytest.fixture(autouse=True)
def disable_redis(monkeypatch):
    monkeypatch.setattr(search_router, "_cache_client", lambda: None)
    yield


def test_search_uses_typesense_results(monkeypatch, authorized_client, sample_posts):
    hits = [
        {"document": {"post_id": sample_posts[1]}},
        {"document": {"post_id": sample_posts[0]}},
    ]
    fake_client = FakeTypesenseClient(hits=hits)
    monkeypatch.setattr(search_router, "get_typesense_client", lambda: fake_client)

    response = authorized_client.post(
        "/search/", json={"query": "Hello", "sort_by": "relevance"}
    )
    assert response.status_code == 200
    data = response.json()
    ids = [post["id"] for post in data["results"]]
    assert ids == [sample_posts[1], sample_posts[0]]


def test_search_falls_back_when_typesense_errors(
    monkeypatch, authorized_client, sample_posts
):
    fake_client = FakeTypesenseClient(should_raise=True)
    monkeypatch.setattr(search_router, "get_typesense_client", lambda: fake_client)

    response = authorized_client.post(
        "/search/", json={"query": "Hello", "sort_by": "relevance"}
    )
    assert response.status_code == 200
    data = response.json()
    ids = [post["id"] for post in data["results"]]
    # default search order uses DB order (score desc) but should include both posts
    assert set(ids) == {sample_posts[0], sample_posts[1]}
