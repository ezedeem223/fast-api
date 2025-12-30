import app.analytics as analytics


def test_merge_stats_numeric_and_type_conflicts():
    base = {"a": 1, "b": "text", "c": 2}
    incoming = {"a": 4, "b": 3, "d": 5}
    merged = analytics.merge_stats(base, incoming)
    assert merged["a"] == 5  # sums numeric
    assert merged["b"] == 3  # overwrites different type
    assert merged["c"] == 2
    assert merged["d"] == 5


def test_merge_stats_handles_none_inputs():
    merged = analytics.merge_stats(None, None)
    assert merged == {}
    merged2 = analytics.merge_stats(None, {"x": 1})
    assert merged2 == {"x": 1}


def test_analyze_sentiment_happy_path(monkeypatch):
    def fake_pipeline():
        return lambda text: [{"label": "POSITIVE", "score": 0.9}]

    monkeypatch.setattr(analytics, "_get_sentiment_pipeline", fake_pipeline)
    result = analytics.analyze_sentiment("great day")
    assert result == {"sentiment": "POSITIVE", "score": 0.9}


def test_analyze_sentiment_fallback_on_error(monkeypatch):
    def boom():
        raise RuntimeError("load failed")

    monkeypatch.setattr(analytics, "_get_sentiment_pipeline", boom)
    result = analytics.analyze_sentiment("any text")
    assert result == {"sentiment": "NEUTRAL", "score": 0.0}


def test_analyze_sentiment_empty_text_is_neutral():
    result = analytics.analyze_sentiment("")
    assert result == {"sentiment": "NEUTRAL", "score": 0.0}


def test_suggest_improvements_paths():
    negative = {"sentiment": "NEGATIVE", "score": 0.81}
    short = {"sentiment": "POSITIVE", "score": 0.5}
    neutral = {"sentiment": "POSITIVE", "score": 0.9}

    assert (
        "positive tone" in analytics.suggest_improvements("bad text", negative).lower()
    )
    assert "short" in analytics.suggest_improvements("too short", short).lower()
    long_text = (
        "this post is definitely long enough to avoid the short warning path now"
    )
    assert "looks good" in analytics.suggest_improvements(long_text, neutral).lower()
