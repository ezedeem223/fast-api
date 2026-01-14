"""Additional coverage for Redis cache edge cases."""
from __future__ import annotations

import asyncio

import pytest

import base64
import json

from app.core.cache.redis_cache import RedisCache, cache_key_list, cache_key_user


@pytest.mark.asyncio
async def test_redis_cache_error_paths(monkeypatch):
    """Exercise error branches for delete/invalidate/set_many/get_many/exists/increment/tag invalidation."""
    cache = RedisCache()
    cache.enabled = True

    class BadRedis:
        async def delete(self, *_):
            raise RuntimeError("boom")

        async def scan(self, *_):
            raise RuntimeError("boom")

        def pipeline(self):
            raise RuntimeError("boom")

        async def exists(self, *_):
            raise RuntimeError("boom")

        async def incrby(self, *_):
            raise RuntimeError("boom")

        async def smembers(self, *_):
            raise RuntimeError("boom")

    cache.redis = BadRedis()

    await cache.delete("k")
    await cache.invalidate("pattern")
    await cache.set_many({"k": "v"})
    assert await cache.get_many(["k"]) == {}
    assert await cache.exists("k") is False
    assert await cache.increment("k") == 0
    await cache.invalidate_by_tag("tag")


def test_encode_decode_and_ttl_helpers():
    """Cover encode/decode/compression and TTL override helpers."""
    cache = RedisCache()
    cache._compression_threshold = 1
    encoded = cache._encode_value({"x": 1})
    assert encoded.startswith("1|")
    payload = base64.b64encode(json.dumps({"x": 1}).encode("utf-8")).decode("ascii")
    assert cache._decode_value(f"1|{payload}") == {"x": 1}

    assert cache._decode_value(b"0|1") == 1
    assert cache._decode_value(5) == 5
    assert cache._decode_value("0|{bad}") is None

    override = cache._resolve_ttl("comments:list:1", None)
    assert override == cache.ttl_overrides["comments:list"]

    cache.set_ttl_override("custom", 5)
    assert cache.ttl_overrides["custom"] == 5


def test_invalidate_nowait_runtime_errors(monkeypatch):
    """Ensure invalidate_nowait swallows nested RuntimeError."""
    cache = RedisCache()

    def raise_no_loop():
        raise RuntimeError("no loop")

    def raise_run(coro):
        coro.close()
        raise RuntimeError("run fail")

    monkeypatch.setattr(asyncio, "get_running_loop", raise_no_loop)
    monkeypatch.setattr(asyncio, "run", raise_run)
    result = cache.invalidate_nowait("pattern")
    assert result is None


def test_cache_key_helpers():
    """Cover cache key helpers with and without params."""
    assert cache_key_user("prefs", 1) == "prefs:user:1"
    assert cache_key_user("prefs", 1, lang="ar") == "prefs:user:1:lang=ar"

    assert cache_key_list("posts") == "posts:list"
    assert cache_key_list("posts", page=2, size=10) == "posts:list:page=2_size=10"
