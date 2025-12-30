"""Rate limiting utilities.

Wraps slowapi limiter with a test-friendly no-op variant to keep fixtures deterministic.
Provides a JSON-friendly handler for exceeded limits.
"""

import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from fastapi import Request


class _NoOpLimiter:
    """Disable rate limiting when running tests to keep fixtures deterministic."""

    def limit(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


# Use a no-op limiter in tests to keep fixtures deterministic.
if os.getenv("APP_ENV", settings.environment).lower() == "test":
    limiter = _NoOpLimiter()
else:
    limiter = Limiter(
        key_func=get_remote_address, default_limits=["300 per minute", "5000 per day"]
    )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Return a structured error payload when rate limits are hit."""
    return {
        "error": "rate_limit_exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": exc.detail,
    }
