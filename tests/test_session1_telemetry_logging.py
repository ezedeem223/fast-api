from types import SimpleNamespace

from starlette.testclient import TestClient

from app.core import telemetry
from app.core.middleware import logging_middleware
from app.core.middleware.logging_middleware import LoggingMiddleware
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

# --- Telemetry tests ---


def test_setup_tracing_enabled_with_endpoint(monkeypatch):
    """Ensure OTEL path initializes tracer provider and instruments when enabled with endpoint."""
    calls = SimpleNamespace(
        set_provider=False,
        resource=None,
        exporter=None,
        instrument_app=False,
        requests=False,
        redis=False,
        psycopg=False,
    )

    class FakeTrace:
        def set_tracer_provider(self, provider):
            calls.set_provider = True
            calls.provider = provider

        def get_current_span(self):
            return None

    class FakeResource:
        @classmethod
        def create(cls, data):
            calls.resource = data
            return {"resource": data}

    class FakeProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeExporter:
        def __init__(self, endpoint=None):
            calls.exporter = endpoint

    class FakeProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeFastAPIInstrumentor:
        def instrument_app(self, app):
            calls.instrument_app = True

    class FakeRequestsInstrumentor:
        def instrument(self):
            calls.requests = True

    class FakeRedisInstrumentor:
        def instrument(self):
            calls.redis = True

    class FakePsycopg2Instrumentor:
        def instrument(self):
            calls.psycopg = True

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector")
    monkeypatch.setattr(telemetry, "trace", FakeTrace(), raising=False)
    monkeypatch.setattr(telemetry, "Resource", FakeResource, raising=False)
    monkeypatch.setattr(telemetry, "TracerProvider", FakeProvider, raising=False)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", FakeProcessor, raising=False)
    monkeypatch.setattr(telemetry, "ConsoleSpanExporter", FakeExporter, raising=False)
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", FakeExporter, raising=False)
    monkeypatch.setattr(
        telemetry, "FastAPIInstrumentor", FakeFastAPIInstrumentor, raising=False
    )
    monkeypatch.setattr(
        telemetry, "RequestsInstrumentor", FakeRequestsInstrumentor, raising=False
    )
    monkeypatch.setattr(
        telemetry, "RedisInstrumentor", FakeRedisInstrumentor, raising=False
    )
    monkeypatch.setattr(
        telemetry, "Psycopg2Instrumentor", FakePsycopg2Instrumentor, raising=False
    )

    app = FastAPI()
    telemetry.setup_tracing(app, service_name="svc", enabled=True)

    assert calls.set_provider is True
    assert calls.resource == {"service.name": "svc"}
    assert calls.exporter == "http://collector"
    assert calls.instrument_app is True
    assert calls.requests is True
    assert calls.redis is True
    assert calls.psycopg is True
    assert calls.provider.processors  # one processor attached


def test_setup_tracing_disabled(monkeypatch):
    """When explicitly disabled, tracing should short-circuit without touching OTEL objects."""

    # Ensure any accidental access raises
    class Guard:
        def __getattr__(self, item):
            raise AssertionError("trace should not be accessed when disabled")

    monkeypatch.setattr(telemetry, "trace", Guard())
    telemetry.setup_tracing(
        FastAPI(), service_name="svc", enabled=False
    )  # should not raise


def test_setup_tracing_missing_packages(monkeypatch):
    """When OTEL packages are missing, setup should no-op safely."""
    monkeypatch.setattr(telemetry, "trace", None)
    telemetry.setup_tracing(
        FastAPI(), service_name="svc", enabled=True
    )  # should not raise


def test_setup_sentry_with_dsn(monkeypatch):
    """Sentry initializes when DSN provided and sdk available."""
    calls = {}

    class FakeSentry:
        def init(self, dsn, environment, traces_sample_rate):
            calls["dsn"] = dsn
            calls["env"] = environment
            calls["rate"] = traces_sample_rate

    monkeypatch.setattr(telemetry, "sentry_sdk", FakeSentry())
    telemetry.setup_sentry("dsn-value", environment="prod", traces_sample_rate=0.5)
    assert calls["dsn"] == "dsn-value"
    assert calls["env"] == "prod"
    assert calls["rate"] == 0.5


def test_setup_sentry_without_dsn(monkeypatch):
    """No DSN means no initialization call."""

    class FakeSentry:
        def init(self, *_, **__):
            raise AssertionError("init should not be called")

    monkeypatch.setattr(telemetry, "sentry_sdk", FakeSentry())
    telemetry.setup_sentry(dsn=None, environment="prod")


def test_setup_sentry_missing_sdk(monkeypatch):
    """If SDK missing, skip init gracefully."""
    monkeypatch.setattr(telemetry, "sentry_sdk", None)
    telemetry.setup_sentry("dsn", environment="prod")  # should not raise


# --- Logging middleware tests ---


def _build_test_app(monkeypatch, log_calls, reset_calls, bind_calls):
    """Helper to build a FastAPI app with patched logging hooks."""

    def fake_log_request(**kwargs):
        log_calls.append(kwargs)

    def fake_bind_request_context(**kwargs):
        bind_calls.append(kwargs)
        return [("tok", "val")]

    def fake_reset_request_context(tokens):
        reset_calls.append(tokens)

    monkeypatch.setattr(logging_middleware, "log_request", fake_log_request)
    monkeypatch.setattr(
        logging_middleware, "bind_request_context", fake_bind_request_context
    )
    monkeypatch.setattr(
        logging_middleware, "reset_request_context", fake_reset_request_context
    )

    app = FastAPI()
    app.add_middleware(LoggingMiddleware)
    return app


def test_logging_middleware_success(monkeypatch):
    """Logs successful request with status, duration, and request id header."""
    log_calls, reset_calls, bind_calls = [], [], []
    app = _build_test_app(monkeypatch, log_calls, reset_calls, bind_calls)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/ok")

    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert log_calls and log_calls[0]["status_code"] == 200
    assert log_calls[0]["duration_ms"] >= 0
    assert reset_calls == [[("tok", "val")]]
    assert bind_calls and bind_calls[0]["ip_address"]


def test_logging_middleware_exception(monkeypatch):
    """Even when handlers raise, middleware logs and cleans context."""
    log_calls, reset_calls, bind_calls = [], [], []
    app = _build_test_app(monkeypatch, log_calls, reset_calls, bind_calls)

    @app.get("/fail")
    def fail():
        raise ValueError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/fail")

    assert resp.status_code == 500
    assert log_calls and log_calls[0]["status_code"] == 500
    assert reset_calls == [[("tok", "val")]]
    assert bind_calls  # context binding still happened


def test_logging_middleware_large_response(monkeypatch):
    """Large responses still get logged and header is attached."""
    log_calls, reset_calls, bind_calls = [], [], []
    app = _build_test_app(monkeypatch, log_calls, reset_calls, bind_calls)

    payload = "x" * 50000

    @app.get("/big")
    def big():
        return PlainTextResponse(payload)

    client = TestClient(app)
    resp = client.get("/big")

    assert resp.status_code == 200
    assert resp.text == payload
    assert "X-Request-ID" in resp.headers
    assert log_calls and log_calls[0]["status_code"] == 200
    assert reset_calls == [[("tok", "val")]]
