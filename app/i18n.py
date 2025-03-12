from fastapi import Request
from fastapi_babel import Babel
from deep_translator import GoogleTranslator
from fastapi_cache.decorator import cache
from types import SimpleNamespace

# تهيئة Babel مع تمرير جميع الإعدادات المطلوبة
babel = Babel(
    configs=SimpleNamespace(
        BABEL_DEFAULT_LOCALE="ar", BABEL_DEFAULT_TIMEZONE="UTC", BABEL_DOMAIN="messages"
    )
)

# إنشاء كائن من GoogleTranslator لاستدعاء الدالة get_supported_languages
ALL_LANGUAGES = GoogleTranslator(source="auto", target="en").get_supported_languages(
    as_dict=True
)


def get_locale(request: Request):
    """
    تحديد اللغة المطلوبة من خلال رأس 'Accept-Language'.
    إذا كانت اللغة مدعومة تُعاد؛ وإلا يتم استخدام اللغة الافتراضية المخزنة في حالة التطبيق.
    """
    lang = request.headers.get("Accept-Language", "").split(",")[0].strip()
    return lang if lang in ALL_LANGUAGES else request.app.state.default_language


# تعيين دالة تحديد اللغة يدويًا في كائن Babel
babel.locale_selector = get_locale


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    ترجمة النص من اللغة المصدر إلى اللغة الهدف.
    تُعاد النص الأصلي إذا كانت اللغتين متطابقتين أو في حال فشل الترجمة.
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
    الكشف عن لغة النص باستخدام deep-translator.
    تُعاد 'ar' كلغة افتراضية في حال فشل الكشف.
    """
    try:
        return GoogleTranslator(source="auto", target="en").detect(text)
    except Exception:
        return "ar"


@cache(expire=3600)
async def get_translated_content(text: str, source_lang: str, target_lang: str) -> str:
    """
    ترجمة النص بشكل غير متزامن مع تخزين مؤقت لمدة ساعة.
    """
    return translate_text(text, source_lang, target_lang)
