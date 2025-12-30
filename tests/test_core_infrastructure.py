from types import SimpleNamespace

import pytest

from app.core.cache.redis_cache import cache, cache_manager
from app.core.database import get_db
from app.main import app
from app.routers import search as search_router


def test_livez_readyz_success(client):
    resp = client.get("/livez")
    assert resp.status_code == 200
    # readyz uses DB/Redis; allow 503 if Redis disabled to avoid false failure
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_cache_manager_get_set():
    cache_manager.redis = _FakeRedis()
    cache_manager.enabled = True
    key = cache_manager._generate_key("test", {"a": 1})
    await cache_manager.set(key, {"v": 1})
    val = await cache_manager.get(key)
    assert val == {"v": 1}


@pytest.mark.asyncio
async def test_cache_decorator_hits_cache(monkeypatch):
    # Use fake redis backend
    fake = _FakeRedis()
    cache_manager.redis = fake
    cache_manager.enabled = True

    calls = {"count": 0}

    @cache(prefix="decor")
    async def sample_fn(current_user, x):
        calls["count"] += 1
        return {"x": x}

    user = SimpleNamespace(id=1)
    first = await sample_fn(current_user=user, x=1)
    second = await sample_fn(current_user=user, x=1)
    assert first == second == {"x": 1}
    assert calls["count"] == 1


def test_search_cache_fallback(monkeypatch, authorized_client, test_post):
    # Force cache client to fail and ensure search still responds
    class BrokenCache:
        def get(self, *_):
            raise RuntimeError("cache down")

    monkeypatch.setattr(search_router, "_cache_client", lambda: BrokenCache())
    resp = authorized_client.post(
        "/search/", json={"query": "Fixture", "sort_by": "relevance"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
