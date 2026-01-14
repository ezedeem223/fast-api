"""Coverage tests for Amenhotep AI helpers with safe stubs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai_chat import amenhotep


def _raise_oserror(*args, **kwargs):
    raise OSError("offline")


@pytest.mark.asyncio
async def test_amenhotep_response_and_summary(monkeypatch):
    monkeypatch.setattr(amenhotep.AutoTokenizer, "from_pretrained", _raise_oserror)
    monkeypatch.setattr(amenhotep.AutoModelForCausalLM, "from_pretrained", _raise_oserror)
    monkeypatch.setattr(amenhotep, "pipeline", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        amenhotep,
        "settings",
        SimpleNamespace(HUGGINGFACE_API_TOKEN=""),
    )

    ai = amenhotep.AmenhotepAI(cache_max_size=1)
    ai.knowledge_base = {"general": {"amenhotep": "info"}}
    ai._embed_text = lambda text: [0.1]

    assert ai._contains_arabic("مرحبا") is True
    assert ai._contains_arabic("") is False
    assert ai._normalize_text("Hi!!!") == "hi"

    ai._get_cached_embedding("one")
    ai._get_cached_embedding("two")
    assert len(ai._embedding_cache) == 1

    response = await ai.get_response(user_id=1, message="Amenhotep history")
    assert "info" in response.lower() or "amenhotep" in response.lower()

    summary = ai.get_session_summary(1)
    assert summary["message_count"] >= 1


@pytest.mark.asyncio
async def test_amenhotep_fact_and_generation_paths(monkeypatch):
    monkeypatch.setattr(amenhotep.AutoTokenizer, "from_pretrained", _raise_oserror)
    monkeypatch.setattr(amenhotep.AutoModelForCausalLM, "from_pretrained", _raise_oserror)
    monkeypatch.setattr(amenhotep, "pipeline", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        amenhotep,
        "settings",
        SimpleNamespace(HUGGINGFACE_API_TOKEN=""),
    )

    ai = amenhotep.AmenhotepAI()
    ai.knowledge_base = {}
    ai._get_cached_embedding = lambda text: [0.2]
    ai._build_fact_response = lambda *args, **kwargs: "fact response"

    fact = await ai.get_response(user_id=2, message="unknown topic")
    assert "fact response" in fact

    ai._build_fact_response = lambda *args, **kwargs: None
    ai._generate_with_model = lambda inputs: [[101, 102]]
    ai.tokenizer = SimpleNamespace(
        encode=lambda *args, **kwargs: [101, 102],
        decode=lambda tokens, **kwargs: "generated response",
    )

    generated = await ai.get_response(user_id=2, message="another topic")
    assert "generated response" in generated
