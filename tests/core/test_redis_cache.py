"""Test module for test redis cache session8."""
import asyncio
from types import SimpleNamespace

import pytest

from app.core.cache import redis_cache as rc
from app.core.cache.redis_cache import RedisCache


@pytest.fixture(autouse=True)
def fresh_cache_manager(monkeypatch):
    # Isolate cache manager per test
    """Pytest fixture for fresh_cache_manager."""
    new_manager = RedisCache()
    monkeypatch.setattr(rc, "cache_manager", new_manager)
    yield new_manager


@pytest.mark.asyncio
async def test_init_cache_with_valid_and_invalid_url(monkeypatch, fresh_cache_manager):
    """Test case for test init cache with valid and invalid url."""
    pings = []

    class DummyRedis:
        async def ping(self):
            pings.append(True)

    def fake_from_url(url, **kwargs):
        return DummyRedis()

    monkeypatch.setattr(rc.redis, "from_url", fake_from_url)
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setattr(rc.settings, "REDIS_URL", "redis://example")

    await fresh_cache_manager.init_cache()
    assert fresh_cache_manager.enabled is True
    assert fresh_cache_manager.failed_init is False
    assert isinstance(fresh_cache_manager.redis, DummyRedis)
    assert pings == [True]

    # Simulate invalid URL raising
    def boom(*args, **kwargs):
        raise RuntimeError("bad url")

    monkeypatch.setattr(rc.redis, "from_url", boom)
    await fresh_cache_manager.init_cache()
    assert fresh_cache_manager.enabled is False
    assert fresh_cache_manager.failed_init is True

    # Missing URL leaves disabled but not failed
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(rc.settings, "REDIS_URL", None)
    await fresh_cache_manager.init_cache()
    assert fresh_cache_manager.enabled is False


@pytest.mark.asyncio
async def test_set_get_with_fallback_store(monkeypatch, fresh_cache_manager):
    # Enable cache but provide stub without get/set to trigger fallback
    """Test case for test set get with fallback store."""
    fresh_cache_manager.enabled = True
    fresh_cache_manager.redis = SimpleNamespace()

    await fresh_cache_manager.set("key1", "value1", ttl=1)
    assert await fresh_cache_manager.get("key1") == "value1"

    # Expire via time jump
    monkeypatch.setattr(rc.time, "time", lambda: 1000.0)
    fresh_cache_manager._fallback_store["key1"] = ("value1", 999.0)
    assert await fresh_cache_manager.get("key1") is None


@pytest.mark.asyncio
async def test_set_get_with_real_methods(monkeypatch, fresh_cache_manager):
    """Test case for test set get with real methods."""
    stored = {}

    class DummyRedis:
        def __init__(self):
            self.deleted = []

        async def get(self, key):
            return stored.get(key)

        async def set(self, key, value, ex=None):
            stored[key] = value

        async def delete(self, *keys):
            self.deleted.extend(keys)

        async def scan(self, cursor, match=None, count=None):
            return (0, list(stored.keys()))

    dummy = DummyRedis()
    fresh_cache_manager.enabled = True
    fresh_cache_manager.redis = dummy
    await fresh_cache_manager.set("key2", {"a": 1})
    assert await fresh_cache_manager.get("key2") == {"a": 1}

    await fresh_cache_manager.delete("key2")
    assert dummy.deleted == ["key2"]


@pytest.mark.asyncio
async def test_invalidate_scan(monkeypatch, fresh_cache_manager):
    """Test case for test invalidate scan."""
    keys = {"a:1": "x", "a:2": "y", "b:1": "z"}

    class DummyRedis:
        def __init__(self):
            self.deleted = []

        async def scan(self, cursor, match=None, count=None):
            matched = [k for k in keys if match is None or k.startswith("a:")]
            return (0, matched)

        async def delete(self, *args):
            self.deleted.extend(args)

    dummy = DummyRedis()
    fresh_cache_manager.enabled = True
    fresh_cache_manager.redis = dummy

    await fresh_cache_manager.invalidate("a:*")
    assert set(dummy.deleted) == {"a:1", "a:2"}


@pytest.mark.asyncio
async def test_close_resets_flags(monkeypatch, fresh_cache_manager):
    """Test case for test close resets flags."""
    closed = []

    class DummyRedis:
        def close(self):
            closed.append("sync")

        def aclose(self):
            closed.append("async")
            return asyncio.sleep(0)

    fresh_cache_manager.redis = DummyRedis()
    await fresh_cache_manager.close()
    assert "async" in closed or "sync" in closed
    assert fresh_cache_manager.redis is None
    assert fresh_cache_manager.failed_init is False
