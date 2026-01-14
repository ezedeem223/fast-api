"""Targeted coverage for monitoring and telemetry guards."""
from __future__ import annotations

import importlib
import sys
import types

from fastapi import FastAPI

from app.core import monitoring


def test_count_connections_handles_failure():
    """_count_connections should return 0 when active_connections misbehaves."""
    class BadManager:
        @property
        def active_connections(self):
            raise RuntimeError("boom")

    assert monitoring._count_connections(BadManager()) == 0


def test_setup_monitoring_swallow_ws_errors(monkeypatch):
    """Ensure WS gauge setup errors are swallowed."""
    app = FastAPI()
    monitoring._metrics_configured = False  # type: ignore

    class BoomGauge:
        def labels(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(monitoring, "_ws_connections", BoomGauge())

    monitoring.setup_monitoring(app)
    assert getattr(app.state, "metrics_enabled", False) is True


def test_telemetry_imports_optional_dependencies(monkeypatch):
    """Reload telemetry with stub OTEL/Sentry modules to cover import paths."""
    def _install_module(name, attrs=None):
        module = types.ModuleType(name)
        if attrs:
            for key, value in attrs.items():
                setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    trace_mod = _install_module("opentelemetry.trace", {"set_tracer_provider": lambda *_: None})
    _install_module("opentelemetry", {"trace": trace_mod})

    class DummyExporter:
        def __init__(self, *args, **kwargs):
            pass

    class DummyProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class DummyTracerProvider:
        def __init__(self, *args, **kwargs):
            pass

        def add_span_processor(self, _):
            pass

    class DummyResource:
        @staticmethod
        def create(*_):
            return "resource"

    class DummyInstrumentor:
        def instrument_app(self, *_):
            pass

        def instrument(self):
            pass

    _install_module(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        {"OTLPSpanExporter": DummyExporter},
    )
    _install_module("opentelemetry.instrumentation.fastapi", {"FastAPIInstrumentor": DummyInstrumentor})
    _install_module("opentelemetry.instrumentation.psycopg2", {"Psycopg2Instrumentor": DummyInstrumentor})
    _install_module("opentelemetry.instrumentation.redis", {"RedisInstrumentor": DummyInstrumentor})
    _install_module("opentelemetry.instrumentation.requests", {"RequestsInstrumentor": DummyInstrumentor})
    _install_module("opentelemetry.sdk.resources", {"Resource": DummyResource})
    _install_module("opentelemetry.sdk.trace", {"TracerProvider": DummyTracerProvider})
    _install_module(
        "opentelemetry.sdk.trace.export",
        {"BatchSpanProcessor": DummyProcessor, "ConsoleSpanExporter": DummyExporter},
    )
    _install_module("sentry_sdk", {"init": lambda *_, **__: None})

    telemetry = importlib.reload(importlib.import_module("app.core.telemetry"))
    assert telemetry.trace is not None
