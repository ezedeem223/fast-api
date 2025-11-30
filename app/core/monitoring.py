"""
Prometheus monitoring configuration.
"""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

# Global guard to avoid double-registration when multiple app instances are created in tests.
_metrics_configured = False


def setup_monitoring(app: FastAPI) -> None:
    """
    Setup Prometheus instrumentation.

    This exposes a /metrics endpoint that Prometheus can scrape.
    It automatically collects:
    - http_requests_total
    - http_request_duration_seconds
    - http_requests_created
    """
    global _metrics_configured
    if _metrics_configured or getattr(app.state, "metrics_enabled", False):
        return

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=[
            "/metrics",
            "/healthz",
            "/livez",
            "/readyz",
            "/docs",
            "/openapi.json",
        ],
        env_var_name="ENABLE_METRICS",
        inprogress_name="fastapi_inprogress",
        inprogress_labels=True,
    )

    # Initialize instrumentation
    instrumentator.instrument(app)

    # Expose the metrics endpoint
    instrumentator.expose(app, include_in_schema=False)

    # Mark metrics as configured to avoid duplicate registry errors in tests
    app.state.metrics_enabled = True
    _metrics_configured = True
