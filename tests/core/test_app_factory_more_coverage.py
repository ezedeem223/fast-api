"""Additional coverage for app factory helpers."""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from app.core import app_factory
from app.core.cache.redis_cache import cache_manager
from app.core.config import settings
from app.core.database import get_db
from tests.testclient import TestClient


def test_reset_test_overrides_clears_state(monkeypatch):
    """Reset test overrides should clear host/https settings in test env."""
    monkeypatch.setattr(settings, "environment", "test", raising=False)
    object.__setattr__(settings, "allowed_hosts", ["example.com"])
    object.__setattr__(settings, "force_https", True)

    app_factory._reset_test_overrides()
    assert getattr(settings, "allowed_hosts") is None
    assert getattr(settings, "force_https") is False


def test_readyz_db_fallback_success(monkeypatch):
    """Cover DB fallback path when primary execute fails in test env."""
    app = FastAPI()
    app_factory._register_routes(app)

    class FailingDB:
        def execute(self, *_):
            raise OperationalError("stmt", {}, Exception("fail"))

    async def override_get_db():
        yield FailingDB()

    app.dependency_overrides[get_db] = override_get_db

    class FakeConn:
        def execute(self, *_):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConn()

    monkeypatch.setattr(settings, "environment", "test", raising=False)
    monkeypatch.setattr(
        settings.__class__,
        "get_database_url",
        lambda *_, **__: "sqlite:///:memory:",
    )
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_args, **_kwargs: FakeEngine())
    monkeypatch.setattr(settings, "REDIS_URL", "", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    cache_manager.redis = None
    cache_manager.failed_init = False

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["details"]["database"] == "connected"


def test_readyz_redis_connected(monkeypatch):
    """Ensure redis connected path is reported."""
    app = FastAPI()
    app_factory._register_routes(app)

    class OKDB:
        def execute(self, *_):
            return None

    async def override_get_db():
        yield OKDB()

    app.dependency_overrides[get_db] = override_get_db

    class OKRedis:
        async def ping(self):
            return True

    cache_manager.redis = OKRedis()
    cache_manager.failed_init = False
    monkeypatch.setattr(settings, "REDIS_URL", "redis://example", raising=False)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["details"]["redis"] == "connected"


def test_readyz_redis_failed_init(monkeypatch):
    """Ensure failed_init triggers 503 and redis disconnected status."""
    app = FastAPI()
    app_factory._register_routes(app)

    class OKDB:
        def execute(self, *_):
            return None

    async def override_get_db():
        yield OKDB()

    app.dependency_overrides[get_db] = override_get_db

    cache_manager.redis = None
    cache_manager.failed_init = True
    monkeypatch.setattr(settings, "REDIS_URL", "", raising=False)

    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["detail"]["redis"] == "disconnected"


def test_database_health_check_paths(monkeypatch):
    """Cover healthy/unhealthy database health check responses."""
    app = FastAPI()
    app_factory._register_routes(app)

    class OKDB:
        def execute(self, *_):
            return None

    async def ok_db():
        yield OKDB()

    app.dependency_overrides[get_db] = ok_db
    with TestClient(app) as client:
        resp = client.get("/healthz/database")
    assert resp.json()["status"] == "healthy"

    class BadDB:
        def execute(self, *_):
            raise RuntimeError("boom")

    async def bad_db():
        yield BadDB()

    app.dependency_overrides[get_db] = bad_db
    with TestClient(app) as client:
        resp = client.get("/healthz/database")
    assert resp.json()["status"] == "unhealthy"


def test_mount_static_files_and_translate(monkeypatch, tmp_path):
    """Cover static mount fallback and translate endpoint."""
    app = FastAPI()

    object.__setattr__(settings, "static_root", None)
    object.__setattr__(settings, "uploads_root", None)

    app.state.default_language = "en"
    monkeypatch.setattr(app_factory, "translate_text", lambda *_: "translated")

    app_factory._mount_static_files(app)

    with TestClient(app) as client:
        resp = client.post("/translate", json={"text": "hi", "source_lang": "en"})
    assert resp.json()["translated"] == "translated"
