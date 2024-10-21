from fastapi import Request
from fastapi_babel import Babel
from googletrans import Translator, LANGUAGES
from langdetect import detect
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache

babel = Babel()
translator = Translator()

# قائمة بجميع اللغات المدعومة
ALL_LANGUAGES = {code: name for code, name in LANGUAGES.items()}


@babel.localeselector
def get_locale(request: Request):
    lang = request.headers.get("Accept-Language")
    if lang in ALL_LANGUAGES:
        return lang
    return request.app.state.default_language


def translate_text(text, source_lang, target_lang):
    if source_lang == target_lang:
        return text
    try:
        return translator.translate(text, src=source_lang, dest=target_lang).text
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # إرجاع النص الأصلي في حالة فشل الترجمة


def detect_language(text):
    try:
        return detect(text)
    except:
        return "ar"  # الإنجليزية كلغة افتراضية إذا فشل الكشف


@cache(expire=3600)
async def cached_translate_text(text, source_lang, target_lang):
    return await translate_text(text, source_lang, target_lang)
