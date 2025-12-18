import os
import json
import logging
import importlib
import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.core import logging_config
from app.core.middleware import ip_ban, language as lang_mw


def test_setup_logging_creates_dir_and_sets_level(tmp_path):
    log_dir = tmp_path / "logs"
    logging_config.setup_logging(log_level="WARNING", log_dir=str(log_dir), use_json=False, use_colors=False)
    assert log_dir.exists()
    # ensure root level set
    assert logging.getLogger().level == logging.WARNING
    logger = logging_config.get_logger("test_logger")
    logger.warning("warn message")


def test_json_formatter_includes_fields():
    formatter = logging_config.JSONFormatter()
    record = logging.LogRecord(
        name="tester",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.user_id = 42
    result = json.loads(formatter.format(record))
    assert result["level"] == "INFO"
    assert result["user_id"] == 42
    assert result["message"] == "hello"


@pytest.mark.asyncio
async def test_ip_ban_middleware_allows_and_blocks(monkeypatch):
    class DummyRequest(Request):
        def __init__(self, host):
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": Headers({}).raw,
                "client": (host, 1234),
            }
            super().__init__(scope)

    async def call_next(_):
        return JSONResponse({"ok": True})

    monkeypatch.setattr(ip_ban.settings, "environment", "prod", raising=False)
    monkeypatch.setattr(ip_ban, "get_client_ip", lambda req: req.client.host)
    monkeypatch.setattr(ip_ban, "is_ip_banned", lambda db, ip: ip == "1.1.1.1")

    allowed = await ip_ban.ip_ban_middleware(DummyRequest("2.2.2.2"), call_next)
    assert allowed.status_code == 200
    blocked = await ip_ban.ip_ban_middleware(DummyRequest("1.1.1.1"), call_next)
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_language_middleware_translates(monkeypatch):
    user = type("User", (), {"auto_translate": True, "preferred_language": "fr"})()
    req_scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": Headers({}).raw,
        "client": ("127.0.0.1", 1234),
    }
    request = Request(req_scope)
    request.state.user = user

    class DummyResp:
        headers = {"Content-Type": "application/json"}
        status_code = 200

        async def json(self):
            return {"msg": "hello"}

    async def call_next(_):
        return DummyResp()

    async def fake_translate(text, src, tgt):
        return f"{text}-{tgt}"
    monkeypatch.setattr(lang_mw, "translate_text", fake_translate)

    translated = await lang_mw.language_middleware(request, call_next)
    assert translated.status_code == 200
    assert json.loads(translated.body.decode())["msg"] == "hello-fr"

    # no user -> passthrough
    req_scope2 = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": Headers({}).raw,
        "client": ("127.0.0.1", 1234),
    }
    request2 = Request(req_scope2)
    plain = await lang_mw.language_middleware(request2, call_next)
    assert isinstance(plain, DummyResp)


def test_rate_limit_noop_and_handler(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    rl_module = importlib.reload(importlib.import_module("app.core.middleware.rate_limit"))
    assert hasattr(rl_module.limiter, "limit")

    @rl_module.limiter.limit("1/minute")
    def demo():
        return "ok"

    assert demo() == "ok"

    dummy_exc = type("Exc", (), {"detail": 2})()
    resp = rl_module.rate_limit_exceeded_handler(Request({"type": "http"}), dummy_exc)
    assert resp["error"] == "rate_limit_exceeded"
    assert resp["retry_after"] == 2
