"""Minimal internationalisation helpers used across the project."""

from __future__ import annotations

import os
from typing import Dict

from fastapi import Request

try:  # Optional dependency – the tests work without it.
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover - optional dependency
    GoogleTranslator = None

if os.getenv("TESTING") == "1":  # Disable external calls during tests
    GoogleTranslator = None


ALL_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
}


def get_locale(request: Request) -> str:
    lang_header = request.headers.get("Accept-Language", "").split(",")[0].strip().lower()
    if lang_header in ALL_LANGUAGES:
        return lang_header
    return request.app.state.default_language


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang or not text:
        return text
    if GoogleTranslator is None:  # pragma: no cover - fallback
        return text
    try:
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception:  # pragma: no cover - translation services may be offline
        return text


async def get_translated_content(text: str, source_lang: str, target_lang: str) -> str:
    return translate_text(text, source_lang, target_lang)


def detect_language(text: str) -> str:
    if GoogleTranslator is None:  # pragma: no cover - fallback
        return "en"
    try:
        return GoogleTranslator(source="auto", target="en").detect(text)
    except Exception:  # pragma: no cover
        return "en"


__all__ = [
    "ALL_LANGUAGES",
    "detect_language",
    "get_locale",
    "translate_text",
    "get_translated_content",
]
