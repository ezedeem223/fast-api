"""Test module for test session13 search cache."""
import pytest

from app import models
from app.modules.search import cache as search_cache
from app.modules.search import service as search_service
from app.modules.search import typesense_client


class DummyClient:
    """Test class for DummyClient."""
    def __init__(self):
        self.store = {}
        self.deleted = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        self.deleted.extend(keys)
        for k in keys:
            self.store.pop(k, None)

    def scan_iter(self, match=None):
        for k in list(self.store.keys()):
            if match is None or k.startswith(match.rstrip("*")):
                yield k


def test_search_cache_hit_miss_invalid_json(monkeypatch):
    """Test case for test search cache hit miss invalid json."""
    dummy = DummyClient()
    monkeypatch.setattr(
        search_cache,
        "settings",
        type("Obj", (), {"redis_client": dummy}),
        raising=False,
    )

    assert search_cache.get_cached_json("missing") is None
    search_cache.set_cached_json("key", {"a": 1}, ttl_seconds=1)
    assert search_cache.get_cached_json("key") == {"a": 1}

    dummy.store["bad"] = "not-json"
    assert search_cache.get_cached_json("bad") is None
    assert "bad" in dummy.deleted

    search_cache.invalidate_stats_cache(for_user_id=5)
    assert dummy.deleted  # patterns deleted


def test_search_cache_delete_pattern(monkeypatch):
    """Test case for test search cache delete pattern."""
    dummy = DummyClient()
    dummy.store = {"a:1": "v", "a:2": "v2", "b": "v3"}
    monkeypatch.setattr(
        search_cache,
        "settings",
        type("Obj", (), {"redis_client": dummy}),
        raising=False,
    )
    search_cache.delete_pattern("a:*")
    assert "a:1" not in dummy.store and "a:2" not in dummy.store
    assert "b" in dummy.store


def test_search_service_update_and_suggestions(session):
    """Test case for test search service update and suggestions."""
    search_service.update_search_statistics(session, user_id=1, query="hello")
    search_service.update_search_statistics(session, user_id=1, query="hello")
    stat = (
        session.query(models.SearchStatistics)
        .filter_by(user_id=1, term="hello")
        .first()
    )
    assert stat.searches == 2

    suggestion = models.SearchSuggestion(term="world", usage_count=5)
    session.add(suggestion)
    session.commit()
    suggestions = search_service.update_search_suggestions(session)
    assert suggestions[0].term == "world"


def test_typesense_client_retry_and_disabled(monkeypatch):
    """Test case for test typesense client retry and disabled."""
    # Arrange: disable Typesense and verify the client is None.
    monkeypatch.setattr(
        typesense_client,
        "settings",
        type(
            "Obj",
            (),
            {
                "typesense_enabled": False,
                "typesense_host": "localhost",
                "typesense_port": "8108",
                "typesense_protocol": "http",
                "typesense_api_key": "key",
                "typesense_collection": "posts",
            },
        )(),
        raising=False,
    )
    assert typesense_client.get_typesense_client() is None

    # Act: enable Typesense with a failing HTTP stub to exercise retry path.
    monkeypatch.setattr(
        typesense_client.settings, "typesense_enabled", True, raising=False
    )
    monkeypatch.setattr(
        typesense_client.settings, "typesense_host", "localhost", raising=False
    )
    monkeypatch.setattr(
        typesense_client.settings, "typesense_port", "8108", raising=False
    )
    monkeypatch.setattr(
        typesense_client.settings, "typesense_protocol", "http", raising=False
    )
    monkeypatch.setattr(
        typesense_client.settings, "typesense_api_key", "key", raising=False
    )
    monkeypatch.setattr(
        typesense_client.settings, "typesense_collection", "posts", raising=False
    )

    class DummyResponse:
        def raise_for_status(self):
            raise requests.RequestException("down")

    import requests

    def fake_post(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr(typesense_client.requests, "post", fake_post)
    client = typesense_client.get_typesense_client()
    # Assert: search raises when the transport fails.
    with pytest.raises(requests.RequestException):
        client.search_posts("q")
