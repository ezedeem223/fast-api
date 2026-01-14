"""Application module."""
from types import SimpleNamespace

from deep_translator import GoogleTranslator
from fastapi_babel import Babel
from fastapi_cache.decorator import cache

from fastapi import Request

babel = Babel(
    configs=SimpleNamespace(
        BABEL_DEFAULT_LOCALE="ar", BABEL_DEFAULT_TIMEZONE="UTC", BABEL_DOMAIN="messages"
    )
)

ALL_LANGUAGES = GoogleTranslator(source="auto", target="en").get_supported_languages(
    as_dict=True
)


def get_locale(request: Request):
    """Resolve the requested language from the "Accept-Language" header. If unsupported, fall back to the application's default language."""
    lang = request.headers.get("Accept-Language", "").split(",")[0].strip()
    return lang if lang in ALL_LANGUAGES else request.app.state.default_language


babel.locale_selector = get_locale


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text from source to target language. Returns original text if languages match or translation fails."""
    if source_lang == target_lang:
        return text
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def detect_language(text: str) -> str:
    """Detect the language of text via deep-translator. Returns "ar" as a safe default on failure."""
    try:
        return GoogleTranslator(source="auto", target="en").detect(text)
    except Exception:
        return "ar"


@cache(expire=3600)
async def get_translated_content(text: str, source_lang: str, target_lang: str) -> str:
    """Async wrapper to translate text with caching for one hour."""
    return translate_text(text, source_lang, target_lang)
