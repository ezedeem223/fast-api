# app/core/middleware/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi import Request
from slowapi.errors import RateLimitExceeded

# إعداد limiter مع redis أو memory (حسب الإعدادات)
limiter = Limiter(
    key_func=get_remote_address, default_limits=["300 per minute", "5000 per day"]
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return {
        "error": "rate_limit_exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": exc.detail,
    }
