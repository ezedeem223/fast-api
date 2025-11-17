"""Response header middleware."""

from fastapi import Request

from app.i18n import get_locale


async def add_language_header(request: Request, call_next):
    """
    Add the Content-Language header to responses based on the resolved locale.
    """
    response = await call_next(request)
    response.headers["Content-Language"] = get_locale(request)
    return response
