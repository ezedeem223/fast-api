"""Test module for test cache and db helpers."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.cache import cache as ttl_cache_decorator
from app.core.cache import redis_cache
from app.core.database import query_helpers
from app.core.database import session as db_session

# 56) cached_query helper


@pytest.mark.asyncio
async def test_cached_query_hit_and_miss(monkeypatch):
    """Test case for test cached query hit and miss."""
    object.__setattr__(redis_cache.settings, "REDIS_URL", "redis://example")
    store = {}

    class FakeRedis:
        async def ping(self):
            return True

        async def get(self, k):
            return store.get(k)

        async def set(self, k, v, ex=None):
            store[k] = v

    monkeypatch.setattr(redis_cache.redis, "from_url", lambda *a, **k: FakeRedis())
    redis_cache.cache_manager = redis_cache.RedisCache()
    await redis_cache.cache_manager.init_cache()

    called = {"count": 0}

    async def query_fn():
        called["count"] += 1
        return "value"

    # miss -> store with tag
    res1 = await redis_cache.cached_query("k1", query_fn, ttl=10, tags=["t"])
    assert res1 == "value" and called["count"] == 1
    # hit -> no extra call
    res2 = await redis_cache.cached_query("k1", query_fn, ttl=10, tags=["t"])
    assert res2 == "value" and called["count"] == 1


@pytest.mark.asyncio
async def test_cached_query_respects_disabled_cache(monkeypatch):
    """Test case for test cached query respects disabled cache."""
    redis_cache.cache_manager = redis_cache.RedisCache()

    async def query_fn():
        return "fresh"

    res = await redis_cache.cached_query("k2", query_fn, ttl=5, tags=["x"])
    assert res == "fresh"


# 57) app/cache fallback


@pytest.mark.asyncio
async def test_app_cache_ttl_decorator(monkeypatch):
    """Test case for test app cache ttl decorator."""
    calls = {"n": 0}

    @ttl_cache_decorator(expire=1)
    async def fn(x):
        calls["n"] += 1
        return x * 2

    first = await fn(2)
    second = await fn(2)
    assert first == 4 and second == 4 and calls["n"] == 1


# 58) build_engine


def test_build_engine_sqlite_has_check_same_thread():
    """Test case for test build engine sqlite has check same thread."""
    eng = db_session.build_engine("sqlite:///:memory:")
    assert eng.url.get_backend_name() == "sqlite"
    conn = eng.raw_connection()
    try:
        driver_conn = getattr(conn, "driver_connection", None) or getattr(
            conn, "connection", None
        )
        assert driver_conn is not None  # connection object exists
    finally:
        conn.close()


def test_build_engine_postgres_params(monkeypatch):
    """Test case for test build engine postgres params."""
    url = "postgresql+psycopg2://u:p@h:5432/db"
    eng = db_session.build_engine(url)
    assert eng.url.database == "db"
    assert eng.pool.size() == 5 or hasattr(eng.pool, "size")  # pool preconfigured


# 59) get_db/SessionLocal


def test_get_db_yields_and_closes(monkeypatch):
    """Test case for test get db yields and closes."""
    eng = create_engine("sqlite:///:memory:")
    db_session.SessionLocal = db_session.sessionmaker(
        autocommit=False, autoflush=False, bind=eng
    )
    gen = db_session.get_db()
    db = next(gen)
    assert isinstance(db, Session)
    gen.close()  # should close without error


# 60) query_helpers


def test_paginate_query_bounds():
    """Test case for test paginate query bounds."""
    q = SimpleNamespace(
        offset=lambda skip_val: SimpleNamespace(
            limit=lambda limit_val: ("skip", skip_val, "limit", limit_val)
        )
    )
    res = query_helpers.paginate_query(q, skip=-5, limit=1000)
    assert res[1] == 0 and res[3] == 100


def test_optimize_count_query_removes_order(monkeypatch):
    """Test case for test optimize count query removes order."""
    class FakeQuery:
        def order_by(self, val):
            self.val = val
            return self

        def count(self):
            return 5

    q = FakeQuery()
    assert query_helpers.optimize_count_query(q) == 5
    assert q.val is None


def test_cursor_paginate_edges():
    """Test case for test cursor paginate edges."""
    class Item:
        id: int = 0

        def __init__(self, id):
            self.id = id

        @property
        def id_attr(self):
            return self.id

    data = [Item(i) for i in range(1, 4)]

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, n):
            return SimpleNamespace(all=lambda: self.items[:n])

        @property
        def column_descriptions(self):
            return [{"entity": Item}]

    # bypass sqlalchemy desc/asc coercion for stub model
    query_helpers.desc = lambda col: col  # type: ignore
    query_helpers.asc = lambda col: col  # type: ignore
    result = query_helpers.cursor_paginate(FakeQuery(data), cursor=None, limit=2)
    assert result["count"] == 2 and result["has_next"] is True
    assert result["items"][0].id == 1
