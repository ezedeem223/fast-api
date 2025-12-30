import app.core.telemetry as telemetry


def test_setup_tracing_disabled_logs(monkeypatch, caplog):
    caplog.set_level("INFO")
    telemetry.setup_tracing(app=None, service_name="svc", enabled=False)
    assert any("OpenTelemetry disabled" in rec.message for rec in caplog.records)


def test_setup_tracing_missing_otel(monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setattr(telemetry, "trace", None)
    telemetry.setup_tracing(app=None, service_name="svc", enabled=True)
    assert any("opentelemetry not installed" in rec.message for rec in caplog.records)


def test_setup_tracing_console_and_instrumentors(monkeypatch, caplog):
    caplog.set_level("INFO")
    recorded = {}

    class DummyProvider:
        def __init__(self, resource=None):
            recorded["resource"] = resource
            self.processors = []

        def add_span_processor(self, p):
            self.processors.append(p)

    class DummyTrace:
        def __init__(self):
            self.provider = None

        def set_tracer_provider(self, provider):
            self.provider = provider

        def get_current_span(self):
            return None

    dummy_trace = DummyTrace()

    class DummyExporter:
        def __init__(self, endpoint=None):
            recorded["exporter"] = endpoint or "console"

    class DummyBatch:
        def __init__(self, exporter):
            recorded["batch"] = exporter

    class DummyInstr:
        def instrument_app(self, app):
            recorded["fastapi_app"] = app

    class DummyReqInstr:
        def instrument(self):
            recorded["requests"] = True

    class DummyRedisInstr:
        def instrument(self):
            recorded["redis"] = True

    class DummyPsycopg2Instr:
        def instrument(self):
            recorded["psycopg2"] = True

    class DummyResource:
        @staticmethod
        def create(attrs):
            recorded["resource_attrs"] = attrs
            return "resource"

    telemetry.Resource = DummyResource
    telemetry.TracerProvider = DummyProvider
    telemetry.OTLPSpanExporter = DummyExporter
    telemetry.ConsoleSpanExporter = DummyExporter
    telemetry.BatchSpanProcessor = DummyBatch
    telemetry.FastAPIInstrumentor = lambda: DummyInstr()
    telemetry.RequestsInstrumentor = lambda: DummyReqInstr()
    telemetry.RedisInstrumentor = lambda: DummyRedisInstr()
    telemetry.Psycopg2Instrumentor = lambda: DummyPsycopg2Instr()
    monkeypatch.setattr(telemetry, "trace", dummy_trace)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    telemetry.setup_tracing(app="appobj", service_name="svc", enabled=True)
    assert recorded["resource_attrs"]["service.name"] == "svc"
    assert recorded["exporter"] == "console"
    assert recorded["fastapi_app"] == "appobj"
    assert recorded["requests"] is True
    assert recorded["redis"] is True
    assert recorded["psycopg2"] is True


def test_setup_sentry_no_dsn_noop(caplog):
    caplog.set_level("INFO")
    telemetry.setup_sentry(dsn=None, environment="test")
    assert "Sentry initialized" not in [rec.message for rec in caplog.records]


def test_setup_sentry_missing_package(monkeypatch, caplog):
    caplog.set_level("WARNING")
    monkeypatch.setattr(telemetry, "sentry_sdk", None)
    telemetry.setup_sentry(dsn="http://dsn", environment="test")
    assert any("sentry-sdk not installed" in rec.message for rec in caplog.records)


def test_setup_sentry_initializes(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = {}

    class DummySentry:
        @staticmethod
        def init(dsn, environment, traces_sample_rate):
            calls["dsn"] = dsn
            calls["environment"] = environment
            calls["rate"] = traces_sample_rate

    monkeypatch.setattr(telemetry, "sentry_sdk", DummySentry)
    telemetry.setup_sentry(dsn="http://dsn", environment="prod", traces_sample_rate=0.5)
    assert calls == {"dsn": "http://dsn", "environment": "prod", "rate": 0.5}
