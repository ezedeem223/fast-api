"""Test module for test app factory session7."""
from app.core import app_factory
from app.core.config import settings
from app.core.database import get_db
from fastapi import status
from tests.testclient import TestClient


def test_force_https_redirects_with_allowed_host(monkeypatch):
    """Test case for test force https redirects with allowed host."""
    monkeypatch.setattr(settings, "allowed_hosts", ["testserver"])
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "force_https", True)

    app = app_factory.create_app()
    with TestClient(app, base_url="http://testserver") as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert resp.headers["location"].startswith("https://testserver")


def test_trusted_host_rejects_invalid_host(monkeypatch):
    """Test case for test trusted host rejects invalid host."""
    monkeypatch.setattr(type(settings), "allowed_hosts", None, raising=False)
    monkeypatch.setattr(settings, "allowed_hosts", ["example.com"])
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "force_https", False)

    app = app_factory.create_app()
    with TestClient(app, base_url="http://badhost") as client:
        resp = client.get("/", headers={"host": "invalid.com"}, follow_redirects=False)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid host" in resp.text.lower()


def test_readyz_success_skips_redis(monkeypatch):
    # Ensure Redis is absent and not marked failed.
    """Test case for test readyz success skips redis."""
    from app.core.cache import redis_cache
    from app.main import app

    redis_cache.cache_manager.redis = None
    redis_cache.cache_manager.failed_init = False
    monkeypatch.setattr(settings, "REDIS_URL", "")
    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["details"]["database"] == "connected"
        assert body["details"]["redis"] == "skipped"


def test_readyz_db_failure(monkeypatch):
    """Test case for test readyz db failure."""
    from app.main import app

    class FailingSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("db down")

    def failing_db():
        yield FailingSession()

    app.dependency_overrides[get_db] = failing_db
    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert resp.json()["detail"]["database"] == "disconnected"
    app.dependency_overrides.pop(get_db, None)


def test_readyz_redis_configured_without_client(monkeypatch):
    """Test case for test readyz redis configured without client."""
    from app.core.cache import redis_cache
    from app.main import app

    redis_cache.cache_manager.redis = None
    redis_cache.cache_manager.failed_init = False
    object.__setattr__(settings, "REDIS_URL", "redis://example")
    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = resp.json()["detail"]
        assert detail["redis"].startswith("disconnected")
    object.__setattr__(settings, "REDIS_URL", "")


def test_maybe_train_classifier_skips_in_test(monkeypatch):
    """Test case for test maybe train classifier skips in test."""
    calls = []
    monkeypatch.setattr(app_factory.Path, "exists", lambda p: False)
    monkeypatch.setattr(app_factory.settings, "environment", "test")
    monkeypatch.setattr(
        app_factory, "train_content_classifier", lambda: calls.append("train")
    )
    app_factory._maybe_train_classifier()
    assert calls == []


def test_maybe_train_classifier_runs_when_missing_in_prod(monkeypatch):
    """Test case for test maybe train classifier runs when missing in prod."""
    calls = []
    monkeypatch.setattr(app_factory.Path, "exists", lambda p: False)
    monkeypatch.setattr(app_factory.settings, "environment", "production")
    monkeypatch.setattr(
        app_factory, "train_content_classifier", lambda: calls.append("train")
    )
    app_factory._maybe_train_classifier()
    assert calls == ["train"]


def test_maybe_train_classifier_skips_when_artifacts_exist(monkeypatch):
    """Test case for test maybe train classifier skips when artifacts exist."""
    calls = []

    def fake_exists(path):
        return True

    monkeypatch.setattr(app_factory.Path, "exists", fake_exists)
    monkeypatch.setattr(app_factory.settings, "environment", "production")
    monkeypatch.setattr(
        app_factory, "train_content_classifier", lambda: calls.append("train")
    )
    app_factory._maybe_train_classifier()
    assert calls == []
