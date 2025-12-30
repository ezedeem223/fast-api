"""Language-aware HTTP middleware.

Translates JSON responses based on the authenticated user's preference when enabled.
Runs after routing so it can inspect the resolved user on request.state.
"""

from app.i18n import translate_text
from fastapi import Request
from fastapi.responses import JSONResponse


async def language_middleware(request: Request, call_next):
    """Automatically translate JSON responses based on the authenticated user's preference."""
    response = await call_next(request)

    if (
        "Content-Type" in response.headers
        and "application/json" in response.headers["Content-Type"]
    ):
        user = getattr(request.state, "user", None)
        if user and getattr(user, "auto_translate", False):
            body = await response.json()
            translated_body = await translate_json(body, user.preferred_language)
            return JSONResponse(
                content=translated_body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

    return response


async def translate_json(data, target_lang):
    """Recursively translate JSON-compatible structures into the target language."""
    if isinstance(data, dict):
        return {
            key: await translate_json(value, target_lang) for key, value in data.items()
        }
    if isinstance(data, list):
        return [await translate_json(item, target_lang) for item in data]
    if isinstance(data, str):
        return await translate_text(data, "auto", target_lang)
    return data
