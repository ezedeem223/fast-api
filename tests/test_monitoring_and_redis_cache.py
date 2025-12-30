import pytest

from app.core import monitoring
from app.core.cache import redis_cache
from app.core.config import settings
from fastapi import FastAPI

# ---------------- Monitoring setup ----------------


def test_monitoring_setup_enabled(monkeypatch):
    app = FastAPI()
    # reset guard
    monitoring._metrics_configured = False  # type: ignore
    monitoring.setup_monitoring(app)
    # metrics_enabled flag set
    assert getattr(app.state, "metrics_enabled", False) is True
    # /metrics route registered
    assert any(r.path == "/metrics" for r in app.router.routes)


def test_monitoring_setup_disabled_when_already_set(monkeypatch):
    app = FastAPI()
    app.state.metrics_enabled = True
    monitoring._metrics_configured = True  # type: ignore
    monitoring.setup_monitoring(app)
    # no duplicate registration
    assert getattr(app.state, "metrics_enabled", False) is True


# ---------------- Redis cache ----------------


@pytest.mark.asyncio
async def test_redis_cache_disabled_when_url_missing(monkeypatch):
    object.__setattr__(settings, "REDIS_URL", "")
    cache = redis_cache.RedisCache()
    await cache.init_cache()
    assert cache.enabled is False
    assert cache.redis is None
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_redis_cache_ping_failure(monkeypatch):
    object.__setattr__(settings, "REDIS_URL", "redis://example")

    class BadRedis:
        async def ping(self):
            raise RuntimeError("conn fail")

    monkeypatch.setattr(redis_cache.redis, "from_url", lambda *a, **k: BadRedis())
    cache = redis_cache.RedisCache()
    await cache.init_cache()
    assert cache.enabled is False
    assert await cache.get("x") is None


@pytest.mark.asyncio
async def test_redis_cache_hit_miss(monkeypatch):
    object.__setattr__(settings, "REDIS_URL", "redis://example")
    store = {}

    class FakeRedis:
        async def ping(self):
            return True

        async def get(self, k):
            return store.get(k)

        async def set(self, k, v, ex=None):
            store[k] = v

        async def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

    monkeypatch.setattr(redis_cache.redis, "from_url", lambda *a, **k: FakeRedis())
    cache = redis_cache.RedisCache()
    await cache.init_cache()
    await cache.set("a", {"v": 1})
    assert await cache.get("a") == {"v": 1}
    await cache.delete("a")
    assert await cache.get("a") is None


@pytest.mark.asyncio
async def test_redis_cache_set_many_get_many_and_tags(monkeypatch):
    object.__setattr__(settings, "REDIS_URL", "redis://example")
    store = {}

    class FakePipeline:
        def __init__(self):
            self.ops = []

        def set(self, k, v, ex=None):
            self.ops.append(("set", k, v, ex))
            return self

        def sadd(self, k, v):
            self.ops.append(("sadd", k, v))
            return self

        def expire(self, k, ttl):
            self.ops.append(("expire", k, ttl))
            return self

        def get(self, k):
            self.ops.append(("get", k))
            return self

        async def execute(self):
            results = []
            for op in self.ops:
                if op[0] == "set":
                    _, k, v, ex = op
                    store[k] = v
                    results.append(True)
                elif op[0] == "sadd":
                    _, k, v = op
                    store.setdefault(k, set()).add(v)
                    results.append(True)
                elif op[0] == "expire":
                    results.append(True)
                elif op[0] == "get":
                    _, k = op
                    results.append(store.get(k))
            return results

    class FakeRedis:
        async def ping(self):
            return True

        def pipeline(self):
            return FakePipeline()

        async def get(self, k):
            return store.get(k)

        async def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

        async def scan(self, cursor, match=None, count=None):
            return 0, []

        async def smembers(self, k):
            return store.get(k, set())

    monkeypatch.setattr(redis_cache.redis, "from_url", lambda *a, **k: FakeRedis())
    cache = redis_cache.RedisCache()
    await cache.init_cache()
    await cache.set_many({"k1": {"v": 1}, "k2": {"v": 2}})
    vals = await cache.get_many(["k1", "k2"])
    assert vals["k1"] == {"v": 1} and vals["k2"] == {"v": 2}
    await cache.set_with_tags("k1", {"v": 1}, tags=["t1"], ttl=5)
    await cache.invalidate_by_tag("t1")
    assert await cache.get("k1") is None
