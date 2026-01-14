"""Test module for test core config cache."""
import asyncio
import json
import os
import time

import pytest
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core import app_factory
from app.core.cache import redis_cache
from app.core.config import environment as env_module


def _reset_settings_env(monkeypatch):
    """Helper for  reset settings env."""
    env_module.get_settings.cache_clear()
    # reset global settings reference in app_factory to fresh settings
    monkeypatch.setattr(app_factory, "settings", env_module.get_settings())


def test_app_factory_adds_https_middleware(monkeypatch, tmp_path):
    """Test case for test app factory adds https middleware."""
    _reset_settings_env(monkeypatch)
    monkeypatch.setattr(app_factory.settings, "force_https", True)
    monkeypatch.setattr(app_factory.settings, "static_root", str(tmp_path / "s"))
    monkeypatch.setattr(app_factory.settings, "uploads_root", str(tmp_path / "u"))
    app = app_factory.create_app()
    assert any(m.cls is HTTPSRedirectMiddleware for m in app.user_middleware)


def test_app_factory_trusted_hosts(monkeypatch, tmp_path):
    """Test case for test app factory trusted hosts."""
    _reset_settings_env(monkeypatch)
    monkeypatch.setattr(app_factory.settings, "force_https", False)
    object.__setattr__(app_factory.settings, "allowed_hosts", ["example.com"])
    monkeypatch.setattr(app_factory.settings, "static_root", str(tmp_path / "s"))
    monkeypatch.setattr(app_factory.settings, "uploads_root", str(tmp_path / "u"))
    app = app_factory.create_app()
    assert any(m.cls is TrustedHostMiddleware for m in app.user_middleware)


def test_static_uploads_paths_created(monkeypatch, tmp_path):
    """Test case for test static uploads paths created."""
    _reset_settings_env(monkeypatch)
    static_dir = tmp_path / "static"
    uploads_dir = tmp_path / "uploads"
    monkeypatch.setattr(app_factory.settings, "static_root", str(static_dir))
    monkeypatch.setattr(app_factory.settings, "uploads_root", str(uploads_dir))
    app_factory.create_app()
    assert static_dir.exists() and uploads_dir.exists()


def test_readyz_db_failure_returns_503(monkeypatch, client):
    """Test case for test readyz db failure returns 503."""
    from app.core.database import get_db
    from app.main import app

    class FailingSession:
        def execute(self, *_):
            raise RuntimeError("db down")

    async def failing_db():
        yield FailingSession()

    app.dependency_overrides[get_db] = failing_db
    resp = client.get("/readyz")
    app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 503
    assert resp.json()["detail"]["database"].startswith("disconnected")


def test_readyz_redis_failure_returns_503(monkeypatch, client):
    """Test case for test readyz redis failure returns 503."""
    from app.core.cache.redis_cache import cache_manager

    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

    class FakeRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    cache_manager.redis = FakeRedis()
    resp = client.get("/readyz")
    os.environ.pop("REDIS_URL", None)
    assert resp.status_code == 503
    assert resp.json()["detail"]["redis"].startswith("disconnected")


@pytest.mark.asyncio
async def test_redis_cache_set_many_get_many_and_ttl(monkeypatch):
    """Test case for test redis cache set many get many and ttl."""
    class FakePipe:
        def __init__(self, store):
            self.store = store
            self.ops = []

        def set(self, key, val, ex=None):
            # store serialized JSON string to mimic redis
            self.store[key] = (time.time() + (ex or 1), json.dumps(val))
            return self

        async def execute(self):
            return [
                v if time.time() <= exp else None
                for exp, v in list(self.store.values())
            ]

        def get(self, key):
            self.ops.append(("get", key))
            ttl_val = self.store.get(key)
            if not ttl_val:
                return None
            exp, val = ttl_val
            return val if time.time() <= exp else None

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def pipeline(self):
            return FakePipe(self.store)

        async def get(self, key):
            ttl_val = self.store.get(key)
            if not ttl_val:
                return None
            exp, val = ttl_val
            return val if time.time() <= exp else None

    fake = FakeRedis()
    monkeypatch.setattr(redis_cache.cache_manager, "redis", fake)
    redis_cache.cache_manager.enabled = True

    await redis_cache.cache_manager.set_many({"k1": {"v": 1}}, ttl=1)
    res = await redis_cache.cache_manager.get_many(["k1"])
    v = res.get("k1")
    if isinstance(v, str):
        v = json.loads(v)
    assert v == {"v": 1}
    await asyncio.sleep(1.1)
    res2 = await redis_cache.cache_manager.get_many(["k1"])
    assert res2.get("k1") in (None, {})


@pytest.mark.asyncio
async def test_redis_cache_invalidate_pattern(monkeypatch):
    """Test case for test redis cache invalidate pattern."""
    deleted = []

    class FakeRedis:
        def __init__(self):
            self.keys = ["a:1", "a:2"]

        async def scan(self, cursor, match=None, count=None):
            return (0, self.keys if cursor == 0 else [])

        async def delete(self, *keys):
            deleted.extend(keys)

    fake = FakeRedis()
    monkeypatch.setattr(redis_cache.cache_manager, "redis", fake)
    redis_cache.cache_manager.enabled = True
    await redis_cache.cache_manager.invalidate("a:*")
    assert set(deleted) == {"a:1", "a:2", "tag:a:*"} or set(deleted) == {"a:1", "a:2"}


@pytest.mark.asyncio
async def test_redis_cache_invalid_json(monkeypatch):
    """Test case for test redis cache invalid json."""
    class FakeRedis:
        def __init__(self):
            self.store = {"bad": "not-json"}

        async def get(self, key):
            return self.store.get(key)

    fake = FakeRedis()
    monkeypatch.setattr(redis_cache.cache_manager, "redis", fake)
    redis_cache.cache_manager.enabled = True

    val = await redis_cache.cache_manager.get("bad")
    assert val is None


def test_settings_get_database_url_variants(monkeypatch):
    """Test case for test settings get database url variants."""
    with monkeypatch.context() as m:
        m.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h:5432/db")
        env_module.get_settings.cache_clear()
        cfg = env_module.get_settings()
        assert cfg.get_database_url() == "postgresql+psycopg2://u:p@h:5432/db"

    with monkeypatch.context() as m:
        m.delenv("DATABASE_URL", raising=False)
        m.setenv("DATABASE_HOSTNAME", "h")
        m.setenv("DATABASE_USERNAME", "u")
        m.setenv("DATABASE_PASSWORD", "p")
        m.setenv("DATABASE_NAME", "db")
        env_module.get_settings.cache_clear()
        cfg = env_module.get_settings()
        url = cfg.get_database_url()
        assert url.startswith("postgresql+psycopg2://u:p@h")

    with monkeypatch.context() as m:
        m.setenv("TEST_DATABASE_URL", "sqlite:///./tests/tmp_fallback.db")
        m.delenv("DATABASE_URL", raising=False)
        m.delenv("DATABASE_HOSTNAME", raising=False)
        env_module.get_settings.cache_clear()
        cfg = env_module.get_settings()
        assert cfg.get_database_url(use_test=True).startswith("sqlite:///")


def test_settings_missing_keys_raise(monkeypatch, tmp_path):
    """Test case for test settings missing keys raise."""
    with monkeypatch.context() as m:
        m.setenv("RSA_PRIVATE_KEY_PATH", str(tmp_path / "missing_priv.pem"))
        m.setenv("RSA_PUBLIC_KEY_PATH", str(tmp_path / "missing_pub.pem"))
        env_module.get_settings.cache_clear()
        with pytest.raises(ValueError):
            env_module.get_settings()
