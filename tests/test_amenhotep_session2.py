import builtins
import os

import pytest
import torch

import app.ai_chat.amenhotep as amenhotep_module


class DummyTokenizer:
    def __call__(self, text, return_tensors=None, truncation=None, max_length=None):
        if return_tensors == "pt":
            return {"input_ids": torch.tensor([[1, 2]]), "attention_mask": torch.tensor([[1, 1]])}
        return {"input_ids": [[1]], "attention_mask": [[1]]}

    @property
    def eos_token_id(self):
        return 0


class DummyModel:
    def __call__(self, **kwargs):
        class Out:
            def __init__(self):
                self.last_hidden_state = torch.ones((1, 2, 4))

        return Out()

    def generate(self, inputs, **kwargs):
        return torch.tensor([[1, 2, 3]])


@pytest.fixture(autouse=True)
def amenhotep_token_fixture(monkeypatch):
    # Ensure missing optional token attribute does not break tests.
    try:
        object.__setattr__(amenhotep_module.settings, "HUGGINGFACE_API_TOKEN", "")
    except Exception:
        setattr(amenhotep_module.settings, "HUGGINGFACE_API_TOKEN", "")


@pytest.fixture
def stubbed_model_and_tokenizer(monkeypatch):
    model_calls = []

    def fake_from_pretrained(name, token=None, device_map=None):
        model_calls.append({"name": name, "device_map": device_map})
        return DummyModel()

    monkeypatch.setattr(
        amenhotep_module.AutoTokenizer, "from_pretrained", lambda *a, **k: DummyTokenizer()
    )
    monkeypatch.setattr(
        amenhotep_module.AutoModelForCausalLM, "from_pretrained", fake_from_pretrained
    )
    monkeypatch.setattr(amenhotep_module, "pipeline", lambda *a, **k: "qa-pipeline")
    return model_calls


def test_embedding_cache_ttl_and_eviction(monkeypatch, stubbed_model_and_tokenizer):
    fake_now = {"t": 0.0}
    monkeypatch.setattr(amenhotep_module.time, "time", lambda: fake_now["t"])

    ai = amenhotep_module.AmenhotepAI(cache_ttl=5, cache_max_size=2)
    embed_calls = []
    ai._embed_text = lambda text: embed_calls.append(text) or [text]  # type: ignore[assignment]
    ai.use_onnx = False

    # First compute and cache
    emb_a = ai._get_cached_embedding("a")
    assert emb_a == ["a"]
    assert embed_calls == ["a"]

    # Within TTL -> cached
    fake_now["t"] = 3
    emb_a_cached = ai._get_cached_embedding("a")
    assert emb_a_cached == ["a"]
    assert embed_calls == ["a"]

    # After TTL -> recompute
    fake_now["t"] = 6
    emb_a_new = ai._get_cached_embedding("a")
    assert emb_a_new == ["a"]
    assert embed_calls == ["a", "a"]

    # Fill and evict oldest (a at t=6)
    fake_now["t"] = 7
    ai._get_cached_embedding("b")
    fake_now["t"] = 8
    ai._get_cached_embedding("c")
    assert set(ai._embedding_cache.keys()) == {"b", "c"}
    assert "a" not in ai._embedding_cache


def test_pytorch_init_gpu_and_cpu_paths(monkeypatch, stubbed_model_and_tokenizer):
    # GPU available -> device_map auto
    monkeypatch.setattr(amenhotep_module.torch.cuda, "is_available", lambda: True, raising=False)
    ai_gpu = amenhotep_module.AmenhotepAI()
    assert any(call["device_map"] == "auto" for call in stubbed_model_and_tokenizer)
    assert ai_gpu.model is not None

    # CPU fallback -> device_map None
    stubbed_model_and_tokenizer.clear()
    monkeypatch.setattr(amenhotep_module.torch.cuda, "is_available", lambda: False, raising=False)
    ai_cpu = amenhotep_module.AmenhotepAI()
    assert any(call["device_map"] is None for call in stubbed_model_and_tokenizer)
    assert ai_cpu.model is not None


def test_pytorch_init_failure_raises(monkeypatch):
    monkeypatch.setattr(amenhotep_module.torch.cuda, "is_available", lambda: False, raising=False)
    monkeypatch.setattr(
        amenhotep_module.AutoTokenizer, "from_pretrained", lambda *a, **k: DummyTokenizer()
    )
    monkeypatch.setattr(amenhotep_module, "pipeline", lambda *a, **k: "qa-pipeline")

    def boom(*args, **kwargs):
        raise RuntimeError("load fail")

    monkeypatch.setattr(amenhotep_module.AutoModelForCausalLM, "from_pretrained", boom)
    with pytest.raises(RuntimeError):
        amenhotep_module.AmenhotepAI()


def test_format_royal_response_variations(monkeypatch):
    # Avoid heavy downstream warnings by stubbing pipeline creation here too.
    monkeypatch.setattr(amenhotep_module, "pipeline", lambda *a, **k: "qa-pipeline")
    ai = amenhotep_module.AmenhotepAI()

    # Arabic text preserved
    arabic = "مرحبا بك"
    resp_ar = ai._format_royal_response(arabic)
    assert arabic in resp_ar
    assert any(prefix in resp_ar for prefix in ["My child", "Listen closely", "Allow me to tell you", "Know this", "As the sages say"])

    # English capitalization maintained
    english = "Hello there"
    resp_en = ai._format_royal_response(english)
    assert english in resp_en

    # Symbols do not break formatting
    symbols = "!!!"
    resp_sym = ai._format_royal_response(symbols)
    assert "!!!" in resp_sym
