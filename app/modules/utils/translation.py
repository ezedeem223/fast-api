"""Translation helpers with caching."""

from __future__ import annotations

from typing import Optional

from cachetools import TTLCache

from .common import logger

translation_cache = TTLCache(maxsize=1000, ttl=3600)

try:
    from app.translation import translate_text  # type: ignore
except ImportError:  # pragma: no cover - optional dependency

    async def translate_text(text: str, source_lang: str, target_lang: str):
        raise NotImplementedError("translate_text function is not implemented.")


async def cached_translate_text(text: str, source_lang: str, target_lang: str):
    """Translate text using cache to avoid redundant calls."""
    cache_key = f"{text}:{source_lang}:{target_lang}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    translated_text = await translate_text(text, source_lang, target_lang)
    translation_cache[cache_key] = translated_text
    return translated_text


async def get_translated_content(content: str, user, source_lang: str):
    """
    Return translated content when user prefers a different language.

    Falls back to original content whenever translation is unavailable.
    """
    preferred_language = getattr(user, "preferred_language", None)
    auto_translate = getattr(user, "auto_translate", False)

    if not content or not auto_translate or not preferred_language:
        return content

    if preferred_language == source_lang:
        return content

    try:
        return await cached_translate_text(content, source_lang, preferred_language)
    except NotImplementedError:
        return content
    except Exception:  # pragma: no cover - best-effort fallback
        logger.exception("Translation failed; returning original content.")
        return content


__all__ = ["translation_cache", "cached_translate_text", "get_translated_content"]
