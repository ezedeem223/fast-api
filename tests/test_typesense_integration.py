import pytest

from app import models
from app.routers import search as search_router


class FakeTypesenseClient:
    def __init__(self, post_id: int):
        self.post_id = post_id
        self.calls = []

    def search_posts(self, query: str, limit: int = 10):
        self.calls.append((query, limit))
        return [{"document": {"post_id": self.post_id}}]


@pytest.fixture
def typesense_post(session, test_user):
    post = models.Post(
        title="Hello typesense",
        content="Body",
        owner_id=test_user["id"],
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def test_typesense_search_integration(monkeypatch, authorized_client, typesense_post):
    client = FakeTypesenseClient(post_id=typesense_post.id)
    monkeypatch.setattr(search_router, "get_typesense_client", lambda: client)

    response = authorized_client.post(
        "/search/",
        json={"query": "Hello", "sort_by": "relevance"},
    )
    assert response.status_code == 200
    data = response.json()
    ids = [post["id"] for post in data["results"]]
    assert ids == [typesense_post.id]
    assert client.calls  # ensure the fake client was invoked
