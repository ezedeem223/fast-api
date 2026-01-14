"""Test module for test session4 cache and scheduling."""
import asyncio

import pytest

from app.core.cache import redis_cache
from app.core.config import settings


class DummyRedis:
    """Test class for DummyRedis."""
    def __init__(self):
        # Simple in-memory store to simulate Redis behavior.
        self.store = {}
        self.failed = False

    async def ping(self):
        if self.failed:
            raise RuntimeError("ping failed")
        return True

    async def get(self, key):
        if self.failed:
            raise RuntimeError("down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if self.failed:
            raise RuntimeError("down")
        self.store[key] = value

    async def _set_now(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    async def scan(self, cursor, match=None, count=100):
        keys = [
            k for k in self.store if match is None or k.startswith(match.rstrip("*"))
        ]
        return 0, keys

    class Pipeline:
        def __init__(self, outer):
            self.outer = outer
            self.ops = []

        def set(self, key, value, ex=None):
            self.ops.append(("set", key, value, ex))
            return self

        def get(self, key):
            self.ops.append(("get", key, None, None))
            return self

        def sadd(self, key, member):
            self.ops.append(("sadd", key, member, None))
            return self

        def expire(self, key, ttl):
            self.ops.append(("expire", key, ttl, None))
            return self

        async def execute(self):
            results = []
            for op, key, val, ex in self.ops:
                if op == "set":
                    await self.outer.set(key, val, ex=ex)
                    results.append(True)
                elif op == "get":
                    results.append(await self.outer.get(key))
                elif op == "sadd":
                    self.outer.store.setdefault(key, set()).add(val)
                    results.append(True)
                elif op == "expire":
                    results.append(True)
            self.ops = []
            return results

    def pipeline(self):
        return DummyRedis.Pipeline(self)

    async def smembers(self, key):
        return self.store.get(key, set())

    async def incrby(self, key, amount):
        self.store[key] = str(int(self.store.get(key, "0")) + amount)
        return int(self.store[key])

    async def exists(self, key):
        return 1 if key in self.store else 0

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_redis_cache_set_with_tags_and_invalidate(monkeypatch):
    """Test case for test redis cache set with tags and invalidate."""
    cache = redis_cache.RedisCache()
    dummy = DummyRedis()
    cache.redis = dummy
    cache.enabled = True

    await cache.set_with_tags("post:1", {"id": 1}, tags=["posts", "user:1"], ttl=30)
    assert await cache.get("post:1") == {"id": 1}

    await cache.invalidate_by_tag("posts")
    assert await cache.get("post:1") is None


@pytest.mark.asyncio
async def test_redis_cache_decorator_includes_user_and_caches(monkeypatch):
    """Test case for test redis cache decorator includes user and caches."""
    dummy = DummyRedis()
    cache = redis_cache.RedisCache()
    cache.redis = dummy
    cache.enabled = True
    monkeypatch.setattr(redis_cache, "cache_manager", cache)

    call_counter = {"count": 0}

    @redis_cache.cache(prefix="demo", ttl=10, include_user=True)
    async def demo_func(current_user=None, payload=None):
        call_counter["count"] += 1
        return {"payload": payload}

    user = type("User", (), {"id": 5})()
    first = await demo_func(current_user=user, payload="first")
    second = await demo_func(current_user=user, payload="first")

    assert first == {"payload": "first"}
    assert second == {"payload": "first"}  # cached result
    assert call_counter["count"] == 1


@pytest.mark.asyncio
async def test_cached_query_uses_cache_and_tags(monkeypatch):
    """Test case for test cached query uses cache and tags."""
    dummy = DummyRedis()
    cache = redis_cache.RedisCache()
    cache.redis = dummy
    cache.enabled = True
    monkeypatch.setattr(redis_cache, "cache_manager", cache)

    calls = {"count": 0}

    async def query_fn():
        calls["count"] += 1
        return [{"v": calls["count"]}]

    key = "posts:user:42"
    first = await redis_cache.cached_query(
        key, query_fn, ttl=15, tags=["posts", "user:42"]
    )
    second = await redis_cache.cached_query(
        key, query_fn, ttl=15, tags=["posts", "user:42"]
    )

    assert first == [{"v": 1}]
    assert second == [{"v": 1}]
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_redis_cache_init_without_url_disables(monkeypatch):
    """Test case for test redis cache init without url disables."""
    monkeypatch.setattr(
        redis_cache, "settings", type("Obj", (), {"redis_url": None}), raising=False
    )
    cache = redis_cache.RedisCache()
    await cache.init_cache()
    assert cache.enabled is False


@pytest.mark.asyncio
async def test_redis_cache_hit_miss_and_expiry(monkeypatch):
    """Test case for test redis cache hit miss and expiry."""
    cache = redis_cache.RedisCache()
    dummy = DummyRedis()
    cache.redis = dummy
    cache.enabled = True

    key = "k1"
    assert await cache.get(key) is None  # miss
    await cache.set(key, {"v": 1}, ttl=1)
    assert await cache.get(key) == {"v": 1}  # hit

    # simulate expiry by removing
    await cache.delete(key)
    assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_redis_cache_invalid_json_and_failures(monkeypatch, caplog):
    """Test case for test redis cache invalid json and failures."""
    cache = redis_cache.RedisCache()
    dummy = DummyRedis()
    dummy.store["bad"] = "not-json"
    dummy.failed = True
    cache.redis = dummy
    cache.enabled = True

    # invalid JSON returns None and logs error
    dummy.failed = False
    assert await cache.get("bad") is None

    # failures on set/get handled gracefully
    dummy.failed = True
    await cache.set("k", {"x": 1})
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_redis_cache_delete_invalidate_and_types(monkeypatch):
    """Test case for test redis cache delete invalidate and types."""
    cache = redis_cache.RedisCache()
    dummy = DummyRedis()
    cache.redis = dummy
    cache.enabled = True

    await cache.set("a", {"x": 1})
    await cache.set("b", ["list"])
    await cache.set_many({"c": 3, "d": {"nested": True}})
    assert await cache.get("b") == ["list"]

    await cache.invalidate("a*")
    assert await cache.get("a") is None

    assert (await cache.get_many(["c", "d"]))["d"] == {"nested": True}

    inc = await cache.increment("counter")
    assert inc == 1


def test_scheduler_tasks_handles_missing_services(monkeypatch):
    # environment test -> scheduler not configured
    """Test case for test scheduler tasks handles missing services."""
    settings.environment = "test"
    from app.core.scheduling import tasks as sched_tasks

    assert sched_tasks._configure_scheduler() is None

    # ensure repeat_every decorated functions no-op in test env
    for fn in (
        sched_tasks.update_search_suggestions_task,
        sched_tasks.update_all_post_scores,
        sched_tasks.cleanup_expired_reels_task,
    ):
        result = fn()
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        assert result is None
