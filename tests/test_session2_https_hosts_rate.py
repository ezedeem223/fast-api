import importlib

import pytest
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.testclient import TestClient

from app.core.app_factory import HostRedirectMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@pytest.fixture
def reload_rate_limit(monkeypatch):
    """Reload rate_limit module with a specific APP_ENV and restore afterwards."""
    import os

    from app.core.middleware import rate_limit as rl_module

    original_env = os.environ.get("APP_ENV")

    def _reload(env: str):
        if env is None:
            monkeypatch.delenv("APP_ENV", raising=False)
        else:
            monkeypatch.setenv("APP_ENV", env)
        return importlib.reload(rl_module)

    yield _reload

    # restore environment and module
    if original_env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", original_env)
    importlib.reload(rl_module)


# --- TrustedHost tests ---


def test_trusted_host_allows_and_denies():
    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["good.com"])

    @app.get("/hello")
    def hello():
        return {"hello": "world"}

    client = TestClient(app, base_url="http://good.com")
    # Allowed host
    ok_resp = client.get("/hello")
    assert ok_resp.status_code == 200
    # Disallowed host should be rejected
    bad_resp = client.get("/hello", headers={"host": "bad.com"})
    assert bad_resp.status_code == 400


# --- HTTPS redirect tests ---


def test_host_redirect_middleware_http_to_https():
    app = FastAPI()
    app.add_middleware(HostRedirectMiddleware, allowed_hosts=["good.com"])

    @app.get("/ping")
    def ping():
        return {"pong": True}

    client = TestClient(app, base_url="http://good.com")
    resp = client.get("/ping", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://good.com/ping"


def test_host_redirect_middleware_https_pass_through():
    app = FastAPI()
    app.add_middleware(HostRedirectMiddleware, allowed_hosts=["good.com"])

    @app.get("/ping")
    def ping():
        return {"pong": True}

    client = TestClient(app, base_url="https://good.com")
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


def test_host_redirect_middleware_invalid_host_first():
    app = FastAPI()
    app.add_middleware(HostRedirectMiddleware, allowed_hosts=["allowed.com"])

    @app.get("/ping")
    def ping():
        return {"pong": True}

    client = TestClient(app, base_url="http://bad.com")
    resp = client.get("/ping", follow_redirects=False)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid host"


# --- Rate limit tests ---


def test_rate_limiter_real_limits_and_429(reload_rate_limit):
    rl = reload_rate_limit("production")
    app = FastAPI()
    app.state.limiter = rl.limiter
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: JSONResponse(
            rl.rate_limit_exceeded_handler(request, exc), status_code=429
        ),
    )

    @app.get("/limited")
    @rl.limiter.limit("1/minute")
    def limited(request: Request):
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    first = client.get("/limited")
    second = client.get("/limited")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limit_exceeded"

    # Restore to test defaults for following tests
    reload_rate_limit("test")


def test_rate_limiter_disabled_in_test_env(reload_rate_limit):
    rl = reload_rate_limit("test")
    assert rl.limiter.__class__.__name__ == "_NoOpLimiter"


def test_rate_limiter_keys_per_ip(reload_rate_limit):
    rl = reload_rate_limit("production")
    app = FastAPI()
    app.state.limiter = rl.limiter
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: JSONResponse(
            rl.rate_limit_exceeded_handler(request, exc), status_code=429
        ),
    )

    def key_by_forwarded(request: Request):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "anon"

    @app.get("/limited2")
    @rl.limiter.limit("1/minute", key_func=key_by_forwarded)
    def limited2(request: Request):
        return JSONResponse({"ok": True})

    client = TestClient(app, raise_server_exceptions=False)
    # First IP hits limit
    first = client.get("/limited2", headers={"x-forwarded-for": "1.1.1.1"})
    assert first.status_code == 200
    second = client.get("/limited2", headers={"x-forwarded-for": "1.1.1.1"})
    assert second.status_code == 429
    # Different IP should be allowed (different key)
    third = client.get("/limited2", headers={"x-forwarded-for": "2.2.2.2"})
    assert third.status_code == 200

    reload_rate_limit("test")
