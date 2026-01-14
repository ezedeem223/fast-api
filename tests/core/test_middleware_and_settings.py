"""Test module for test middleware and settings."""
from types import SimpleNamespace

import pytest
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.config.settings import Settings
from app.core.middleware import (
    headers,
    ip_ban,
    language,
    logging_middleware,
    rate_limit,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# ---------------- Middleware: IP ban / language / rate limit -----------------


def _make_app(with_middlewares):
    """Helper for  make app."""
    app = FastAPI()
    for mw in with_middlewares:
        app.add_middleware(BaseHTTPMiddleware, dispatch=mw)

    @app.get("/ok")
    async def ok():
        return {"msg": "ok"}

    return app


def test_ip_ban_blocks(monkeypatch):
    """Test case for test ip ban blocks."""
    monkeypatch.setattr(ip_ban, "get_client_ip", lambda req: "1.2.3.4")
    monkeypatch.setattr(ip_ban, "is_ip_banned", lambda db, ip: True)

    def fake_get_db():
        yield SimpleNamespace()

    monkeypatch.setattr(ip_ban, "get_db", fake_get_db)
    object.__setattr__(settings, "environment", "production")
    app = _make_app([ip_ban.ip_ban_middleware])
    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/ok")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Your IP address is banned"


def test_language_header_and_fallback(monkeypatch):
    # translate_text called but returns original to simulate unsupported language fallback
    """Test case for test language header and fallback."""
    monkeypatch.setattr(headers, "get_locale", lambda req: "fr")
    monkeypatch.setattr(language, "translate_text", lambda text, src, tgt: text)
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=headers.add_language_header)
    app.add_middleware(BaseHTTPMiddleware, dispatch=language.language_middleware)
    from fastapi import Request

    @app.get("/greet")
    async def greet(request: Request):
        request.state.user = SimpleNamespace(
            auto_translate=False, preferred_language="xx"
        )
        from fastapi.responses import PlainTextResponse

        # non-JSON response should skip translation and still set header
        return PlainTextResponse("hello")

    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/greet")
        assert resp.headers["Content-Language"] == "fr"
        assert resp.text == "hello"


def test_rate_limit_disabled(monkeypatch):
    # force no-op limiter
    """Test case for test rate limit disabled."""
    class NoOp:
        def limit(self, *a, **k):
            def deco(fn):
                return fn

            return deco

    monkeypatch.setattr(rate_limit, "limiter", NoOp())
    app = FastAPI()

    @app.get("/limited")
    @rate_limit.limiter.limit("1/minute")
    def limited():
        return {"ok": True}

    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/limited")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_rate_limit_enabled_handles_exception(monkeypatch):
    """Test case for test rate limit enabled handles exception."""
    monkeypatch.setenv("APP_ENV", "production")
    app = FastAPI()
    app.add_exception_handler(
        RateLimitExceeded,
        lambda req, exc: JSONResponse(
            {"error": "rate_limit_exceeded"}, status_code=429
        ),
    )

    class DummyLimit:
        error_message = "too many"

    @app.get("/limited")
    def limited():
        raise RateLimitExceeded(DummyLimit())

    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/limited")
        assert resp.status_code == 429
        assert resp.json()["error"] == "rate_limit_exceeded"


# ---------------- LoggingMiddleware -----------------


def test_logging_middleware_success_logs(monkeypatch):
    """Test case for test logging middleware success logs."""
    calls = []
    monkeypatch.setattr(logging_middleware, "log_request", lambda **k: calls.append(k))
    app = FastAPI()
    app.add_middleware(logging_middleware.LoggingMiddleware)

    @app.get("/ping")
    def ping():
        return {"pong": True}

    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/ping")
        assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["status_code"] == 200
    assert "duration_ms" in calls[0]


def test_logging_middleware_exception_logs(monkeypatch):
    """Test case for test logging middleware exception logs."""
    calls = []
    monkeypatch.setattr(logging_middleware, "log_request", lambda **k: calls.append(k))
    app = FastAPI()
    app.add_middleware(logging_middleware.LoggingMiddleware)

    @app.get("/err")
    def err():
        raise HTTPException(status_code=418)

    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/err")
        assert resp.status_code == 418
    assert calls and calls[0]["status_code"] == 418


# ---------------- Settings get_database_url -----------------


def _make_dummy_settings(**overrides):
    """Helper for  make dummy settings."""
    dummy = SimpleNamespace(
        database_url=None,
        database_hostname=None,
        database_username=None,
        database_password=None,
        database_name=None,
        database_port=5432,
        database_ssl_mode=None,
        test_database_url=None,
    )
    for k, v in overrides.items():
        setattr(dummy, k, v)

    def _get_database_url(use_test: bool = False):
        return Settings.get_database_url(dummy, use_test=use_test)

    def _resolve_test():
        return Settings._resolve_test_database_url(dummy)

    dummy.get_database_url = _get_database_url
    dummy._resolve_test_database_url = _resolve_test
    return dummy


def test_get_database_url_uses_explicit_test():
    """Test case for test get database url uses explicit test."""
    s = _make_dummy_settings(test_database_url="sqlite:///./explicit_test.db")
    assert s.get_database_url(use_test=True) == "sqlite:///./explicit_test.db"


def test_get_database_url_builds_postgres_and_test_suffix():
    """Test case for test get database url builds postgres and test suffix."""
    s = _make_dummy_settings(
        database_hostname="db",
        database_username="u",
        database_password="p",
        database_name="main",
        database_port=5432,
        database_ssl_mode="require",
    )
    test_url = s._resolve_test_database_url()
    assert "main_test" in test_url
    assert "sslmode=require" in test_url
    # runtime DB url without test flag uses same base minus _test
    runtime_url = s.get_database_url()
    assert "main_test" not in runtime_url and "main" in runtime_url


def test_get_database_url_fallback_sqlite():
    """Test case for test get database url fallback sqlite."""
    s = _make_dummy_settings()
    s.test_database_url = None
    s.database_url = None
    assert s._resolve_test_database_url().startswith("sqlite:///")
    with pytest.raises(ValueError):
        s.get_database_url()


def test_get_database_url_rejects_non_test_db_name(monkeypatch):
    """Test case for test get database url rejects non test db name."""
    s = _make_dummy_settings(test_database_url="postgresql://x/y")

    # simulate non *_test name by overriding resolver
    def bad_resolve():
        return "postgresql://prod_db"

    s._resolve_test_database_url = bad_resolve
    with pytest.raises(ValueError):
        s.get_database_url(use_test=True)
