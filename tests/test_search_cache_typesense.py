"""Covers search cache (Redis-like) helpers and Typesense client fallback without real network/Redis."""

import fnmatch

from app.core.config import settings
from app.modules.search import cache as search_cache
from app.modules.search import typesense_client


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def scan_iter(self, match="*"):
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, match.replace("*", "*")):
                yield key


def test_search_cache_set_get_delete(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(search_cache, "_client", lambda: fake)

    key = search_cache.popular_cache_key(5)
    search_cache.set_cached_json(key, {"k": 1}, ttl_seconds=10)
    assert search_cache.get_cached_json(key) == {"k": 1}

    search_cache.delete_keys([key])
    assert search_cache.get_cached_json(key) is None


def test_search_cache_invalid_json(monkeypatch):
    fake = FakeRedis()
    fake.setex("bad", 10, "not-json")
    monkeypatch.setattr(search_cache, "_client", lambda: fake)
    assert search_cache.get_cached_json("bad") is None
    assert "bad" not in fake.store


def test_invalidate_stats_cache(monkeypatch):
    fake = FakeRedis()
    fake.setex("search:stats:user:1:10", 10, "{}")
    fake.setex("search:stats:popular:5", 10, "{}")
    fake.setex("other:key", 10, "{}")
    monkeypatch.setattr(search_cache, "_client", lambda: fake)

    search_cache.invalidate_stats_cache(for_user_id=1)
    assert "other:key" in fake.store
    assert not any(k.startswith("search:stats") for k in fake.store)


def test_typesense_client_disabled(monkeypatch):
    monkeypatch.setattr(settings, "typesense_enabled", False)
    assert typesense_client.get_typesense_client() is None


def test_typesense_search(monkeypatch):
    # Enable and reset cached client to force a fresh TypesenseClient creation.
    monkeypatch.setattr(settings, "typesense_enabled", True)
    monkeypatch.setattr(typesense_client, "_cached_client", None)
    monkeypatch.setattr(settings, "typesense_host", "h")
    monkeypatch.setattr(settings, "typesense_port", "8108")
    monkeypatch.setattr(settings, "typesense_protocol", "http")
    monkeypatch.setattr(settings, "typesense_api_key", "k")
    monkeypatch.setattr(settings, "typesense_collection", "c")

    calls = {"count": 0}

    class FakeResp:
        def __init__(self):
            self._json = {"hits": [{"document": {"post_id": 1}}]}

        def raise_for_status(self):
            return None

        def json(self):
            calls["count"] += 1
            return self._json

    def fake_post(*args, **kwargs):
        return FakeResp()

    monkeypatch.setattr(typesense_client.requests, "post", fake_post)

    client = typesense_client.get_typesense_client()
    hits = client.search_posts("hi", limit=5)
    assert hits == [{"document": {"post_id": 1}}]
    assert calls["count"] == 1

    # Cached client should be reused to avoid extra HTTP calls once constructed.
    assert typesense_client.get_typesense_client() is client
