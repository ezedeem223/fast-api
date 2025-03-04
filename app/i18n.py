from fastapi import Request
from fastapi_babel import Babel
from deep_translator import GoogleTranslator
from fastapi_cache.decorator import cache

babel = Babel()

# Dictionary of supported languages by Google Translator
ALL_LANGUAGES = GoogleTranslator.get_supported_languages(as_dict=True)


@babel.localeselector
def get_locale(request: Request):
    """
    Determine the locale from the 'Accept-Language' header.
    If the language is supported, return it; otherwise, use the app's default language.
    """
    lang = request.headers.get("Accept-Language", "").split(",")[0].strip()
    return lang if lang in ALL_LANGUAGES else request.app.state.default_language


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text from the source language to the target language.
    Returns the original text if the source and target languages are the same or if translation fails.
    """
    if source_lang == target_lang:
        return text
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def detect_language(text: str) -> str:
    """
    Detect the language of the given text using `deep-translator`.
    Returns 'ar' as the default if detection fails.
    """
    try:
        return GoogleTranslator().detect(text)
    except Exception:
        return "ar"


@cache(expire=3600)
async def cached_translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Asynchronously translate text with caching for 1 hour.
    """
    return translate_text(text, source_lang, target_lang)
