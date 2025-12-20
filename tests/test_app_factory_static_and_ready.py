from types import SimpleNamespace


from tests.testclient import TestClient

from app.core import app_factory
from app.core.config import settings
from app.core.cache import redis_cache


def _build_app(monkeypatch, static_root: str, uploads_root: str):
    # ensure no classifier training or startup tasks run
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)
    object.__setattr__(settings, "static_root", static_root)
    object.__setattr__(settings, "uploads_root", uploads_root)
    return app_factory.create_app()


def test_static_uploads_fallback_creates_dirs(monkeypatch, tmp_path):
    bogus_static = tmp_path / "nope" / "static"
    bogus_uploads = tmp_path / "nope" / "uploads"
    app = _build_app(monkeypatch, str(bogus_static), str(bogus_uploads))
    assert bogus_static.exists()
    assert bogus_uploads.exists()
    with TestClient(app) as client:
        resp = client.get("/static/")
        assert resp.status_code in (200, 404)
        resp2 = client.get("/uploads/")
        assert resp2.status_code in (200, 404)


def test_cache_control_added_only_on_200(monkeypatch, tmp_path):
    static_dir = tmp_path / "static"
    uploads_dir = tmp_path / "uploads"
    static_dir.mkdir()
    uploads_dir.mkdir()
    # create a file for 200 response
    (static_dir / "hello.txt").write_text("hi")
    object.__setattr__(settings, "static_cache_control", "public, max-age=60")
    object.__setattr__(settings, "uploads_cache_control", "public, max-age=120")
    app = _build_app(monkeypatch, str(static_dir), str(uploads_dir))
    with TestClient(app) as client:
        ok = client.get("/static/hello.txt")
        assert ok.status_code == 200
        assert ok.headers["cache-control"] == "public, max-age=60"
        missing = client.get("/static/missing.txt")
        assert missing.status_code == 404
        assert "cache-control" not in missing.headers


def test_readyz_database_paths(monkeypatch):
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)

    def good_execute(sql):
        return True

    def bad_execute(sql):
        raise RuntimeError("db down")

    class FakeRedis:
        async def ping(self):
            return True

    # ensure redis init is no-op during lifespan
    async def noop():
        return None

    monkeypatch.setattr(redis_cache.cache_manager, "init_cache", noop)
    monkeypatch.setattr(redis_cache.cache_manager, "close", noop)
    monkeypatch.setattr(redis_cache.cache_manager, "redis", None)

    def fake_get_db_bad():
        yield SimpleNamespace(execute=bad_execute)

    def fake_get_db_good():
        yield SimpleNamespace(execute=good_execute)

    # DB failure
    monkeypatch.setattr(app_factory, "get_db", fake_get_db_bad)
    monkeypatch.setattr(redis_cache, "cache_manager", redis_cache.cache_manager)
    app = app_factory.create_app()
    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["detail"]["database"] == "disconnected"

    # DB success
    monkeypatch.setattr(app_factory, "get_db", fake_get_db_good)
    monkeypatch.setattr(redis_cache, "cache_manager", redis_cache.cache_manager)
    app_ok = app_factory.create_app()
    with TestClient(app_ok) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200


def test_readyz_redis_paths(monkeypatch):
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)
    object.__setattr__(settings, "REDIS_URL", "redis://example")

    async def noop():
        return None

    monkeypatch.setattr(redis_cache.cache_manager, "init_cache", noop)
    monkeypatch.setattr(redis_cache.cache_manager, "close", noop)

    def good_execute(sql):
        return True

    class FakePing:
        async def ping(self):
            return True

    class BadPing:
        async def ping(self):
            raise RuntimeError("ping fail")

    # REDIS_URL set but client None -> 503
    def fake_get_db():
        yield SimpleNamespace(execute=good_execute)

    monkeypatch.setattr(app_factory, "get_db", fake_get_db)
    monkeypatch.setattr(redis_cache, "cache_manager", redis_cache.cache_manager)
    monkeypatch.setattr(app_factory, "cache_manager", redis_cache.cache_manager)
    app1 = app_factory.create_app()
    with TestClient(app1) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["detail"]["redis"].startswith("disconnected")

    # REDIS_URL empty -> skipped
    object.__setattr__(settings, "REDIS_URL", "")
    monkeypatch.setattr(app_factory, "get_db", fake_get_db)
    monkeypatch.setattr(redis_cache, "cache_manager", redis_cache.cache_manager)
    monkeypatch.setattr(app_factory, "cache_manager", redis_cache.cache_manager)
    app2 = app_factory.create_app()
    with TestClient(app2) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["details"]["redis"] == "skipped"

    # ping failure logged -> 503
    object.__setattr__(settings, "REDIS_URL", "redis://example")
    monkeypatch.setattr(app_factory, "get_db", fake_get_db)
    async def async_noop():
        return None

    cm = SimpleNamespace(redis=BadPing(), init_cache=async_noop, close=async_noop)
    monkeypatch.setattr(redis_cache, "cache_manager", cm)
    monkeypatch.setattr(app_factory, "cache_manager", cm)
    app3 = app_factory.create_app()
    with TestClient(app3) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["detail"]["redis"] == "disconnected"
