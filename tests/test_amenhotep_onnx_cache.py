import types

import numpy as np
import pytest
import torch


def _build_module(monkeypatch, use_onnx: bool):
    import app.ai_chat.amenhotep as amenhotep_module

    class DummyTokenizer:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def encode(self, text, **kwargs):
            return torch.tensor([[1, 2, 3]])

        def __call__(self, text, return_tensors=None, **kwargs):
            self.calls += 1
            if return_tensors == "np":
                return {
                    "input_ids": np.array([[1, 2, 3]]),
                    "attention_mask": np.array([[1, 1, 1]]),
                }
            return {
                "input_ids": torch.tensor([[1, 2, 3]]),
                "attention_mask": torch.tensor([[1, 1, 1]]),
            }

        @property
        def eos_token_id(self):
            return 0

        def decode(self, *_, **__):
            return "decoded"

    class DummyModel:
        def __call__(self, **kwargs):
            return types.SimpleNamespace(last_hidden_state=torch.ones(1, 2, 4))

        def generate(self, inputs, **kwargs):
            return torch.tensor([[4, 5, 6]])

    class DummySession:
        def __init__(self):
            self.run_calls = 0

        def run(self, *_args, **_kwargs):
            self.run_calls += 1
            return [np.array([[0.1, 0.2, 0.3]])]

    monkeypatch.setattr(
        amenhotep_module,
        "AutoTokenizer",
        types.SimpleNamespace(from_pretrained=lambda *a, **k: DummyTokenizer()),
    )
    monkeypatch.setattr(
        amenhotep_module,
        "AutoModelForCausalLM",
        types.SimpleNamespace(from_pretrained=lambda *a, **k: DummyModel()),
    )
    monkeypatch.setattr(
        amenhotep_module, "pipeline", lambda *a, **k: lambda *_, **__: {}
    )
    monkeypatch.setattr(
        amenhotep_module,
        "os",
        types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: use_onnx),
            makedirs=lambda *_, **__: None,
        ),
    )
    monkeypatch.setattr(
        amenhotep_module, "settings", types.SimpleNamespace(HUGGINGFACE_API_TOKEN=None)
    )
    if use_onnx:
        monkeypatch.setattr(
            amenhotep_module,
            "ort",
            types.SimpleNamespace(InferenceSession=lambda *_, **__: DummySession()),
        )
    else:
        monkeypatch.setattr(amenhotep_module, "ort", None)
    return amenhotep_module, DummySession, DummyModel, DummyTokenizer


def test_embedding_cache_reuses_onnx(monkeypatch):
    mod, DummySession, _, DummyTokenizer = _build_module(monkeypatch, use_onnx=True)
    session_instance = DummySession()
    monkeypatch.setattr(mod.ort, "InferenceSession", lambda *_, **__: session_instance)

    ai = mod.AmenhotepAI(onnx_path="fake.onnx", cache_ttl=100, cache_max_size=4)
    emb1 = ai._get_cached_embedding("hello")
    emb2 = ai._get_cached_embedding("hello")
    assert emb1 == emb2
    assert session_instance.run_calls == 1  # cached second call
    assert isinstance(emb1, list)


def test_fallback_to_torch_embedding(monkeypatch):
    mod, _, DummyModel, DummyTokenizer = _build_module(monkeypatch, use_onnx=False)
    ai = mod.AmenhotepAI(onnx_path="missing.onnx", cache_ttl=10, cache_max_size=2)
    emb = ai._get_cached_embedding("hi torch")
    # mean of ones tensor shape (1,2,4) -> length 4 list of 1.0s
    assert all(abs(x - 1.0) < 1e-6 for x in emb)
    assert len(emb) == 4


@pytest.mark.asyncio
async def test_generate_response_uses_cache(monkeypatch):
    mod, DummySession, _, DummyTokenizer = _build_module(monkeypatch, use_onnx=True)
    ai = mod.AmenhotepAI(onnx_path="fake.onnx", cache_ttl=100, cache_max_size=4)
    resp = await ai.get_response(user_id=1, message="unknown topic text")
    assert isinstance(resp, str)
    # embedding cache should contain the message
    assert "unknown topic text" in ai._embedding_cache
