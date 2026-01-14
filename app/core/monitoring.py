"""Prometheus monitoring configuration with duplicate-registration guard.

Instrumentation is optional and guarded to avoid duplicate registry errors when multiple
app instances are created in tests or interactive sessions.
"""

from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge

from fastapi import FastAPI

# Global guard to avoid double-registration when multiple app instances are created in tests.
_metrics_configured = False
_ws_connections = Gauge(
    "app_ws_connections",
    "Active websocket connections by channel",
    ["channel"],
)


def _count_connections(manager) -> int:
    """Helper for  count connections."""
    try:
        return sum(len(sockets) for sockets in manager.active_connections.values())
    except Exception:
        return 0


def setup_monitoring(app: FastAPI) -> None:
    """Attach Prometheus instrumentation once per process/test run.

    Exposes `/metrics` for scraping and collects request totals, duration, and in-flight gauges.
    Uses a global flag and app.state marker to avoid duplicate registration during tests.
    """
    global _metrics_configured
    if _metrics_configured or getattr(app.state, "metrics_enabled", False):
        # Avoid double registration when test suites instantiate multiple app instances.
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

    # Attach websocket connection gauges when managers are available.
    try:
        from app.notifications import manager as notifications_manager

        _ws_connections.labels(channel="notifications").set_function(
            lambda m=notifications_manager: _count_connections(m)
        )
    except Exception:
        pass

    try:
        from app.routers import call as call_router

        _ws_connections.labels(channel="calls").set_function(
            lambda m=call_router.manager: _count_connections(m)
        )
    except Exception:
        pass

    try:
        from app.routers import call_signaling as signaling_router

        _ws_connections.labels(channel="call_signaling").set_function(
            lambda m=signaling_router.call_manager: _count_connections(m)
        )
    except Exception:
        pass

    # Mark metrics as configured to avoid duplicate registry errors in tests
    app.state.metrics_enabled = True
    _metrics_configured = True
