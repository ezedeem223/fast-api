"""Test module for test resilience."""
import pytest

from app import models
from app.routers import search as search_router


class FailingCache:
    """Test class for FailingCache."""
    def get(self, key):
        raise RuntimeError("cache down")


@pytest.fixture
def sample_posts(session, test_user):
    """Pytest fixture for sample_posts."""
    posts = []
    for idx in range(2):
        post = models.Post(
            title=f"Resilience {idx}",
            content=f"Body {idx}",
            owner_id=test_user["id"],
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        posts.append(post)
    return posts


def test_search_handles_cache_failure(monkeypatch, authorized_client, sample_posts):
    # Force cache client to raise and ensure the endpoint still responds
    """Test case for test search handles cache failure."""
    monkeypatch.setattr(search_router, "_cache_client", lambda: FailingCache())

    response = authorized_client.post(
        "/search/",
        json={"query": "Hello", "sort_by": "relevance"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


@pytest.mark.parametrize(
    "content,expected_detail",
    [
        ("", "Message content cannot be empty"),
        ("x" * 1001, "Message content exceeds the maximum length of 1000 characters"),
    ],
)
def test_message_validation_limits(
    authorized_client, test_user2, content, expected_detail
):
    """Test case for test message validation limits."""
    response = authorized_client.post(
        "/message/",
        json={"recipient_id": test_user2["id"], "content": content},
    )
    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


def test_post_creation_survives_economy_failure(monkeypatch, authorized_client):
    # Force SocialEconomyService to throw during post creation to simulate DB interruption.
    """Test case for test post creation survives economy failure."""
    monkeypatch.setattr(
        "app.modules.social.economy_service.SocialEconomyService.update_post_score",
        lambda self, post_id: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(
        "app.modules.social.economy_service.SocialEconomyService.check_and_award_badges",
        lambda self, user_id: None,
    )
    res = authorized_client.post(
        "/posts/", json={"title": "Resilient", "content": "Even if economy fails"}
    )
    assert res.status_code in (200, 201)
    assert res.json()["title"] == "Resilient"
