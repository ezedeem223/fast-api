from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core import app_factory
from app.core.config import settings
from tests.testclient import TestClient


def _build_app(monkeypatch, force_https: bool, allowed_hosts):
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)
    object.__setattr__(settings, "force_https", force_https)
    object.__setattr__(settings, "allowed_hosts", allowed_hosts)
    return app_factory.create_app()


def test_force_https_enabled_adds_middleware(monkeypatch):
    app = _build_app(monkeypatch, True, ["*"])
    assert any(mw.cls is HTTPSRedirectMiddleware for mw in app.user_middleware)


def test_force_https_disabled_not_added(monkeypatch):
    app = _build_app(monkeypatch, False, ["*"])
    assert not any(mw.cls is HTTPSRedirectMiddleware for mw in app.user_middleware)


def test_trusted_host_added(monkeypatch):
    allowed = ["example.com"]
    app = _build_app(monkeypatch, False, allowed)
    assert any(mw.cls is TrustedHostMiddleware for mw in app.user_middleware)
    with TestClient(app, base_url="http://example.com") as client:
        assert client.get("/").status_code == 200


def test_trusted_host_blocks_disallowed(monkeypatch):
    app = _build_app(monkeypatch, False, ["example.com"])
    with TestClient(app, base_url="http://example.com") as client:
        ok = client.get("/", headers={"host": "example.com"})
        assert ok.status_code == 200
        bad = client.get("/", headers={"host": "evil.com"})
        assert bad.status_code == 400
