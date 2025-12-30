import os
from types import SimpleNamespace

import pytest
import torch

import app.ai_chat.amenhotep as amenhotep_module


class DummyTokenizer:
    def __init__(self):
        self.decode_calls = []

    def encode(self, text, return_tensors=None, max_length=None, truncation=None):
        return ["encoded"]

    def decode(self, outputs, skip_special_tokens=True):
        self.decode_calls.append(outputs)
        return "decoded-output"

    def __call__(self, text, return_tensors=None, truncation=None, max_length=None):
        if return_tensors == "np":
            return {"input_ids": [[1, 2]], "attention_mask": [[1, 1]]}
        if return_tensors == "pt":
            return {
                "input_ids": torch.tensor([[1, 2]]),
                "attention_mask": torch.tensor([[1, 1]]),
            }
        return {"input_ids": [1], "attention_mask": [1]}

    @property
    def eos_token_id(self):
        return 0


class DummyModel:
    def __init__(self):
        self.generate_called = 0
        self.call_count = 0

    def generate(self, inputs, **kwargs):
        self.generate_called += 1
        return torch.tensor([[1, 2, 3]])

    def __call__(self, **kwargs):
        self.call_count += 1

        class Out:
            def __init__(self):
                self.last_hidden_state = torch.ones((1, 2, 4))

        return Out()


@pytest.fixture
def amenhotep_stubs(monkeypatch):
    tokenizer = DummyTokenizer()
    model_calls = {"count": 0}

    def fake_model_from_pretrained(*args, **kwargs):
        model_calls["count"] += 1
        return DummyModel()

    monkeypatch.setattr(
        amenhotep_module.AutoTokenizer, "from_pretrained", lambda *a, **k: tokenizer
    )
    monkeypatch.setattr(
        amenhotep_module.AutoModelForCausalLM,
        "from_pretrained",
        fake_model_from_pretrained,
    )
    monkeypatch.setattr(amenhotep_module, "pipeline", lambda *a, **k: "qa-pipeline")
    monkeypatch.setattr(
        amenhotep_module.torch.cuda, "is_available", lambda: False, raising=False
    )
    # Ensure optional token attribute exists to avoid AttributeError in settings.
    try:
        object.__setattr__(amenhotep_module.settings, "HUGGINGFACE_API_TOKEN", "")
    except Exception:
        setattr(amenhotep_module.settings, "HUGGINGFACE_API_TOKEN", "")
    return SimpleNamespace(tokenizer=tokenizer, model_calls=model_calls)


def test_amenhotep_prefers_onnx_when_available(monkeypatch, tmp_path, amenhotep_stubs):
    onnx_path = tmp_path / "model.onnx"
    onnx_path.write_text("dummy")

    class DummySession:
        def __init__(self, *args, **kwargs):
            self.run_called = False

        def run(self, *args, **kwargs):
            self.run_called = True
            return [[[0.1, 0.2]]]

    monkeypatch.setattr(
        amenhotep_module,
        "ort",
        SimpleNamespace(InferenceSession=DummySession),
    )

    real_exists = os.path.exists
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda path: (
            True if os.fspath(path) == os.fspath(onnx_path) else real_exists(path)
        ),
    )

    # If PyTorch model is touched here we want to know.
    monkeypatch.setattr(
        amenhotep_module.AutoModelForCausalLM,
        "from_pretrained",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Should not init torch model")
        ),
        raising=True,
    )

    ai = amenhotep_module.AmenhotepAI(onnx_path=str(onnx_path))
    assert ai.use_onnx is True
    assert isinstance(ai.onnx_session, DummySession)
    assert ai.model is None


@pytest.mark.parametrize(
    "onnx_exists, session_raises",
    [
        (False, False),  # path missing -> skip ONNX
        (True, True),  # corrupt session -> fallback
    ],
)
def test_amenhotep_falls_back_when_onnx_unusable(
    monkeypatch, tmp_path, amenhotep_stubs, onnx_exists, session_raises
):
    onnx_path = tmp_path / "broken.onnx"
    if onnx_exists:
        onnx_path.write_text("broken")

    def fake_inference_session(*args, **kwargs):
        if session_raises:
            raise RuntimeError("corrupt onnx")
        return SimpleNamespace(run=lambda *a, **k: [[[0.5]]])

    monkeypatch.setattr(
        amenhotep_module,
        "ort",
        SimpleNamespace(InferenceSession=fake_inference_session),
    )

    real_exists = os.path.exists
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda path: (
            True
            if os.fspath(path) == os.fspath(onnx_path) and onnx_exists
            else real_exists(path)
        ),
    )

    ai = amenhotep_module.AmenhotepAI(onnx_path=str(onnx_path))
    assert ai.use_onnx is False
    assert ai.model is not None
    assert amenhotep_stubs.model_calls["count"] == 1


@pytest.mark.asyncio
async def test_amenhotep_session_trims_and_caches(monkeypatch, amenhotep_stubs):
    ai = amenhotep_module.AmenhotepAI()
    ai.knowledge_base = {}
    ai._format_royal_response = lambda x: x

    cache_calls = {"count": 0}
    gen_calls = {"count": 0}

    def fake_get_cached_embedding(text):
        cache_calls["count"] += 1
        return [0.1, 0.2]

    def fake_generate_with_model(inputs):
        gen_calls["count"] += 1
        return [["tok"]]

    ai._get_cached_embedding = fake_get_cached_embedding  # type: ignore[assignment]
    ai._generate_with_model = fake_generate_with_model  # type: ignore[assignment]

    user_id = 1
    for i in range(12):
        await ai.get_response(user_id=user_id, message=f"msg{i}")

    context = ai.session_context[user_id]
    assert len(context) == 10
    assert context[0]["role"] == "user" and context[0]["content"] == "msg7"
    assert (
        context[-1]["role"] == "assistant"
        and context[-1]["content"] == "decoded-output"
    )
    assert cache_calls["count"] == 12
    assert gen_calls["count"] == 12


@pytest.mark.asyncio
async def test_amenhotep_uses_knowledge_base_before_model(monkeypatch, amenhotep_stubs):
    ai = amenhotep_module.AmenhotepAI()
    ai._format_royal_response = lambda x: x
    ai.knowledge_base = {"general": {"pyramids": "stone secrets"}}

    ai._get_cached_embedding = lambda *_: (_ for _ in ()).throw(AssertionError("cache should not be used"))  # type: ignore[assignment]
    ai._generate_with_model = lambda *_: (_ for _ in ()).throw(AssertionError("model should not be used"))  # type: ignore[assignment]

    resp = await ai.get_response(user_id=2, message="Tell me about pyramids today")
    assert resp == "stone secrets"

    # Now drop knowledge base to force model path.
    embed_calls = {"count": 0}
    gen_calls = {"count": 0}
    ai.knowledge_base = {}
    ai._get_cached_embedding = lambda *_: embed_calls.__setitem__("count", embed_calls["count"] + 1) or [0.2]  # type: ignore[assignment]
    ai._generate_with_model = lambda *_: (gen_calls.__setitem__("count", gen_calls["count"] + 1)) or [["tok2"]]  # type: ignore[assignment]

    resp2 = await ai.get_response(user_id=2, message="no match topic")
    assert resp2 == "decoded-output"
    assert embed_calls["count"] == 1
    assert gen_calls["count"] == 1
