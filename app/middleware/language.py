from fastapi import Request
from fastapi.responses import JSONResponse
from ..i18n import translate_text
from ..models import User


async def language_middleware(request: Request, call_next):
    response = await call_next(request)

    if (
        "Content-Type" in response.headers
        and "application/json" in response.headers["Content-Type"]
    ):
        user = request.state.user if hasattr(request.state, "user") else None
        if user and user.auto_translate:
            body = await response.json()
            translated_body = await translate_json(body, user.preferred_language)
            return JSONResponse(
                content=translated_body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

    return response


async def translate_json(data, target_lang):
    if isinstance(data, dict):
        return {k: await translate_json(v, target_lang) for k, v in data.items()}
    elif isinstance(data, list):
        return [await translate_json(item, target_lang) for item in data]
    elif isinstance(data, str):
        return await translate_text(data, "auto", target_lang)
    else:
        return data
