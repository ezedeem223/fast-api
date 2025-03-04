from fastapi import Request
from fastapi_babel import Babel
from googletrans import Translator, LANGUAGES
from langdetect import detect
from fastapi_cache.decorator import cache

babel = Babel()
translator = Translator()

# Supported languages dictionary
ALL_LANGUAGES = {code: name for code, name in LANGUAGES.items()}


@babel.localeselector
def get_locale(request: Request):
    """
    Determine the locale from the 'Accept-Language' header.
    Returns the language code if supported, otherwise the app's default language.
    """
    lang = request.headers.get("Accept-Language")
    if lang in ALL_LANGUAGES:
        return lang
    return request.app.state.default_language


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text from source_lang to target_lang.
    Returns the original text if source and target are the same or translation fails.
    """
    if source_lang == target_lang:
        return text
    try:
        return translator.translate(text, src=source_lang, dest=target_lang).text
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def detect_language(text: str) -> str:
    """
    Detect the language of the given text.
    Returns 'ar' as default if detection fails.
    """
    try:
        return detect(text)
    except Exception:
        return "ar"


@cache(expire=3600)
async def cached_translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Asynchronously translate text with caching for 1 hour.
    """
    return translate_text(text, source_lang, target_lang)
