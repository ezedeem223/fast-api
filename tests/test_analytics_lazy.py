import pytest

import app.analytics as analytics


@pytest.fixture(autouse=True)
def reset_pipeline(monkeypatch):
    monkeypatch.setattr(analytics, "_sentiment_pipeline", None, raising=False)
    monkeypatch.setattr(analytics, "model", None, raising=False)


def test_sentiment_pipeline_lazy_loading(monkeypatch):
    calls = {"tokenizer": 0, "model": 0, "pipeline": 0}

    class DummyTokenizer:
        @staticmethod
        def from_pretrained(name):
            calls["tokenizer"] += 1
            return f"tokenizer:{name}"

    class DummyModel:
        @staticmethod
        def from_pretrained(name):
            calls["model"] += 1
            return f"model:{name}"

    def fake_pipeline(task, model=None, tokenizer=None):
        calls["pipeline"] += 1

        class DummyPipeline:
            def __call__(self, text):
                return [{"label": "POSITIVE", "score": 0.9}]

        return DummyPipeline()

    monkeypatch.setattr(analytics, "AutoTokenizer", DummyTokenizer)
    monkeypatch.setattr(analytics, "AutoModelForSequenceClassification", DummyModel)
    monkeypatch.setattr(analytics, "pipeline", fake_pipeline)

    first = analytics.analyze_sentiment("hello world")
    assert first["sentiment"] == "POSITIVE"
    assert calls == {"tokenizer": 1, "model": 1, "pipeline": 1}

    second = analytics.analyze_sentiment("another")
    assert second["sentiment"] == "POSITIVE"
    # pipeline reused, no additional loads
    assert calls == {"tokenizer": 1, "model": 1, "pipeline": 1}
