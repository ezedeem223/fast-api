import sys
import types
import pytest

dummy_tf = types.ModuleType("transformers")
dummy_tf.pipeline = lambda *a, **k: (lambda text: [{"label": "POSITIVE", "score": 1.0}])
dummy_tf.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **k: object())
dummy_tf.AutoModelForSequenceClassification = types.SimpleNamespace(from_pretrained=lambda *a, **k: object())
sys.modules.setdefault("transformers", dummy_tf)

from app.modules.utils import content


def test_sanitize_text_removes_scripts():
    dirty = "<script>alert('x')</script>Hello <b>World</b>"
    cleaned = content.sanitize_text(dirty)
    assert "script" not in cleaned.lower()
    assert "Hello World" in cleaned


def test_safe_analyze_fallback_on_failure(monkeypatch, caplog):
    caplog.set_level("ERROR")

    def boom():
        raise RuntimeError("no model")

    monkeypatch.setattr(content, "_get_sentiment_pipeline", boom)
    result = content.safe_analyze("text to analyze")
    assert result["sentiment"] == "unknown"
    assert any("safe_analyze_failed" in rec.message for rec in caplog.records)


def test_safe_analyze_handles_empty_and_truncates(monkeypatch):
    # stub pipeline to avoid heavy model load
    class DummyPipeline:
        def __call__(self, text):
            return [{"label": "POSITIVE", "score": 1.0}]

    monkeypatch.setattr(content, "_get_sentiment_pipeline", lambda: DummyPipeline())
    result = content.safe_analyze("")
    assert result["sentiment"] == "neutral"
    long_text = "a" * 600
    result2 = content.safe_analyze(long_text, max_length=10)
    assert len(result2["text"]) == 10


def test_antivirus_scan_logs_on_failure(caplog):
    caplog.set_level("ERROR")

    def bad_scan(_):
        raise RuntimeError("scanner down")

    ok = content.antivirus_scan(b"data", scanner=bad_scan)
    assert ok is False
    assert any("antivirus_scan_failed" in rec.message for rec in caplog.records)
