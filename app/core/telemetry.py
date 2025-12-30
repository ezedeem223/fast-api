"""
Lightweight telemetry wiring (OpenTelemetry + optional Sentry).

Safe defaults:
- If opentelemetry packages are missing or OTEL is disabled, we no-op.
- If SENTRY_DSN is unset or sentry-sdk is missing, we no-op.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:  # Optional OTEL import
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
except Exception:  # pragma: no cover - optional dependency
    trace = None

try:  # Optional Sentry import
    import sentry_sdk
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None

logger = logging.getLogger(__name__)


def setup_tracing(app, service_name: str, enabled: bool = True) -> None:
    """Initialize OpenTelemetry tracing if dependencies and configuration exist.

    Designed to be safe in constrained environments: missing OTEL deps or disabled flags
    simply skip setup without failing the app. Instrumentation is idempotent.
    """
    if not enabled:
        logger.info("OpenTelemetry disabled via configuration.")
        return

    if trace is None:
        logger.info("opentelemetry not installed; skipping tracing.")
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Prefer OTLP export; fall back to console for quick visibility.
    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    else:
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Instrument common components; instrumentation is idempotent.
    FastAPIInstrumentor().instrument_app(app)
    try:
        RequestsInstrumentor().instrument()
    except Exception:  # pragma: no cover - optional
        logger.debug("Requests instrumentation failed; continuing.", exc_info=True)
    try:
        RedisInstrumentor().instrument()
    except Exception:  # pragma: no cover - optional
        logger.debug("Redis instrumentation failed; continuing.", exc_info=True)
    try:
        Psycopg2Instrumentor().instrument()
    except Exception:  # pragma: no cover - optional
        logger.debug("Psycopg2 instrumentation failed; continuing.", exc_info=True)

    logger.info(
        "OpenTelemetry tracing configured.",
        extra={"otel_endpoint": otlp_endpoint or "console"},
    )


def setup_sentry(
    dsn: Optional[str], environment: str, traces_sample_rate: float = 0.1
) -> None:
    """Initialize Sentry if DSN is provided and sentry-sdk is installed."""
    if not dsn:
        return
    if sentry_sdk is None:
        logger.warning(
            "Sentry DSN provided but sentry-sdk not installed; skipping Sentry setup."
        )
        return
    sentry_sdk.init(
        dsn=dsn, environment=environment, traces_sample_rate=traces_sample_rate
    )
    logger.info("Sentry initialized.")
