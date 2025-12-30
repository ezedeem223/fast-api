"""Response header middleware.

Ensures every response carries `Content-Language` derived from request locale resolution.
"""

from app.i18n import get_locale
from fastapi import Request


async def add_language_header(request: Request, call_next):
    """Add the Content-Language header to responses based on the resolved locale."""
    response = await call_next(request)
    response.headers["Content-Language"] = get_locale(request)
    return response
