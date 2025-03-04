# app/middleware/language.py

from fastapi import Request
from fastapi.responses import JSONResponse
from ..i18n import translate_text  # Function to translate text
from ..models import User


async def language_middleware(request: Request, call_next):
    """
    Middleware to automatically translate JSON responses based on the user's preferred language.
    """
    # Process the request and obtain the response from the next middleware or endpoint
    response = await call_next(request)

    # Check if the response content type is JSON
    if (
        "Content-Type" in response.headers
        and "application/json" in response.headers["Content-Type"]
    ):
        # Retrieve the user from the request state if available
        user = request.state.user if hasattr(request.state, "user") else None
        if user and user.auto_translate:
            # Parse the JSON body of the response
            body = await response.json()
            # Translate the JSON content to the user's preferred language
            translated_body = await translate_json(body, user.preferred_language)
            # Return a new JSON response with the translated content
            return JSONResponse(
                content=translated_body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

    # Return the original response if translation is not needed
    return response


async def translate_json(data, target_lang):
    """
    Recursively translate JSON data into the target language.
    """
    if isinstance(data, dict):
        return {k: await translate_json(v, target_lang) for k, v in data.items()}
    elif isinstance(data, list):
        return [await translate_json(item, target_lang) for item in data]
    elif isinstance(data, str):
        # Translate string data using the translate_text function
        return await translate_text(data, "auto", target_lang)
    else:
        return data
