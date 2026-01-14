"""Test module for test session8 cache."""
import asyncio

import pytest

from app import cache as local_cache
from app.core.cache import redis_cache


def test_local_cache_decorator_hit_and_args(monkeypatch):
    """Test case for test local cache decorator hit and args."""
    call_counter = {"count": 0}

    @local_cache.cache(expire=60)
    async def add(a, b):
        call_counter["count"] += 1
        return a + b

    first = asyncio.run(add(1, 2))
    second = asyncio.run(add(1, 2))
    third = asyncio.run(add(2, 3))

    assert first == 3 and second == 3
    # Different args should yield a different cache key.
    assert third == 5
    assert call_counter["count"] == 2  # cached once, recomputed once for new args


@pytest.mark.asyncio
async def test_cached_query_disabled_runs_function(monkeypatch):
    # disable cache manager to force cache miss path
    """Test case for test cached query disabled runs function."""
    monkeypatch.setattr(redis_cache.cache_manager, "enabled", False, raising=False)
    calls = {"count": 0}

    async def query_fn():
        calls["count"] += 1
        return calls["count"]

    first = await redis_cache.cached_query("key", query_fn, ttl=5)
    second = await redis_cache.cached_query("key", query_fn, ttl=5)
    assert first == 1 and second == 2
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_redis_cache_init_failure_disables(monkeypatch, caplog):
    """Test case for test redis cache init failure disables."""
    cache = redis_cache.RedisCache()
    monkeypatch.setattr(
        redis_cache,
        "settings",
        type("Obj", (), {"redis_url": "redis://bad"}),
        raising=False,
    )
    monkeypatch.setattr(
        redis_cache.redis,
        "from_url",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connect fail")),
    )
    await cache.init_cache()
    assert cache.enabled is False
