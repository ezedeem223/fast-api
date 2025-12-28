import pytest

from app.modules.search import cache as search_cache


class DummyRedis:
    def __init__(self):
        self.store = {}
        self.ttl = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl[key] = ttl

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
            self.ttl.pop(k, None)

    def scan_iter(self, match=None):
        prefix = match.rstrip("*") if match and match.endswith("*") else match
        for k in list(self.store.keys()):
            if prefix is None or k.startswith(prefix):
                yield k


def test_popular_recent_cache_roundtrip(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(
        search_cache,
        "settings",
        type("Obj", (), {"redis_client": dummy}),
        raising=False,
    )

    key_pop = search_cache.popular_cache_key(5)
    key_recent = search_cache.recent_cache_key(3)
    search_cache.set_cached_json(key_pop, {"items": [1, 2]}, ttl_seconds=60)
    search_cache.set_cached_json(key_recent, {"items": []}, ttl_seconds=120)

    assert search_cache.get_cached_json(key_pop) == {"items": [1, 2]}
    assert search_cache.get_cached_json(key_recent) == {"items": []}
    assert dummy.ttl[key_pop] == 60
    assert dummy.ttl[key_recent] == 120


def test_user_cache_invalidation(monkeypatch):
    dummy = DummyRedis()
    dummy.store = {
        "search:stats:user:1:10": "a",
        "search:stats:user:2:10": "b",
        "search:stats:popular:5": "p",
        "search:stats:recent:5": "r",
    }
    monkeypatch.setattr(
        search_cache,
        "settings",
        type("Obj", (), {"redis_client": dummy}),
        raising=False,
    )

    search_cache.invalidate_stats_cache(for_user_id=1)
    assert "search:stats:user:1:10" not in dummy.store
    # untouched for other users
    assert "search:stats:user:2:10" in dummy.store
    # popular/recent evicted too
    assert "search:stats:popular:5" not in dummy.store
    assert "search:stats:recent:5" not in dummy.store


def test_fail_open_without_redis(monkeypatch):
    monkeypatch.setattr(search_cache, "settings", type("Obj", (), {"redis_client": None}), raising=False)
    # get returns None and set/delete do not raise
    assert search_cache.get_cached_json("k") is None
    search_cache.set_cached_json("k", {"v": 1}, ttl_seconds=1)
    search_cache.delete_pattern("search:*")
    search_cache.invalidate_stats_cache(for_user_id=5)
