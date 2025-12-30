"""Logging middleware for FastAPI.

Adds a per-request UUID, enriches log records with user/IP/contextvars, and measures
latency. Optional OpenTelemetry span attributes are set when OTEL is present. Designed
to run early in the stack so downstream middleware/routers inherit the request context.
"""

import time
import uuid
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging_config import (
    bind_request_context,
    log_request,
    reset_request_context,
)
from fastapi import Request, Response

try:  # Optional OpenTelemetry span enrichment
    from opentelemetry import trace
except Exception:  # pragma: no cover - optional dependency
    trace = None


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log HTTP requests/responses with timing and trace-friendly metadata."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Extract user ID if authenticated
        user_id = None
        if hasattr(request.state, "user"):
            user_id = getattr(request.state.user, "id", None)

        # Get client IP
        ip_address = request.client.host if request.client else "unknown"

        tokens = bind_request_context(
            request_id=request_id, user_id=user_id, ip_address=ip_address
        )

        if trace:
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("http.request_id", request_id)
                span.set_attribute("http.client_ip", ip_address)
                span.set_attribute("http.route", request.url.path)
                if user_id is not None:
                    span.set_attribute("enduser.id", user_id)

        # Start timing
        start_time = time.time()

        response: Optional[Response] = None
        try:
            response = await call_next(request)
        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log the request
            log_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code if response else 500,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_id=user_id,
                request_id=request_id,
            )

            # Reset contextvars no matter what
            reset_request_context(tokens)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
