from types import SimpleNamespace

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.middleware.logging_middleware import LoggingMiddleware


def build_app_with_logging(extra_middleware=None):
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)
    if extra_middleware:
        for mw in extra_middleware:
            app.add_middleware(mw)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/with-user")
    async def with_user():
        return {"user": True}

    return app


def test_logging_middleware_sets_request_id_and_logs(monkeypatch):
    logged = []
    tokens_reset = []

    def fake_bind(**kwargs):
        logged.append(("bind", kwargs))
        return ["token1", "token2"]

    def fake_log_request(**kwargs):
        logged.append(("log", kwargs))

    def fake_reset(tokens):
        tokens_reset.append(tokens)

    monkeypatch.setattr(
        "app.core.middleware.logging_middleware.bind_request_context", fake_bind
    )
    monkeypatch.setattr(
        "app.core.middleware.logging_middleware.log_request", fake_log_request
    )
    monkeypatch.setattr(
        "app.core.middleware.logging_middleware.reset_request_context", fake_reset
    )

    app = build_app_with_logging()
    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/ok")

    assert resp.status_code == 200
    req_id = resp.headers.get("X-Request-ID")
    assert req_id
    # bind_request_context called with request_id and ip
    bind_call = logged[0][1]
    assert bind_call["request_id"] == req_id
    assert "ip_address" in bind_call
    log_call = [entry for entry in logged if entry[0] == "log"][0][1]
    assert log_call["method"] == "GET"
    assert log_call["endpoint"] == "/ok"
    assert log_call["status_code"] == 200
    assert log_call["request_id"] == req_id
    assert log_call["duration_ms"] >= 0
    assert tokens_reset == [["token1", "token2"]]


def test_logging_middleware_sets_span_attributes_and_user(monkeypatch):
    span_attrs = {}

    class DummySpan:
        def is_recording(self):
            return True

        def set_attribute(self, key, value):
            span_attrs[key] = value

    class DummyTracer:
        @staticmethod
        def get_current_span():
            return DummySpan()

    logged = []

    def fake_log_request(**kwargs):
        logged.append(kwargs)

    monkeypatch.setattr("app.core.middleware.logging_middleware.trace", DummyTracer)
    monkeypatch.setattr(
        "app.core.middleware.logging_middleware.log_request", fake_log_request
    )

    class UserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = SimpleNamespace(id=5)
            return await call_next(request)

    app = build_app_with_logging(extra_middleware=[UserMiddleware])
    from tests.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/with-user")

    assert resp.status_code == 200
    req_id = resp.headers.get("X-Request-ID")
    assert span_attrs["http.request_id"] == req_id
    assert span_attrs["http.route"] == "/with-user"
    assert span_attrs["enduser.id"] == 5
    assert "http.client_ip" in span_attrs
    assert logged[0]["user_id"] == 5
    assert logged[0]["endpoint"] == "/with-user"
