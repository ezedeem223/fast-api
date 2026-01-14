"""Test module for test analytics logging."""
import importlib
import sys
import types


def _load_analytics_with_stubbed_transformers():
    """Helper for  load analytics with stubbed transformers."""
    dummy = types.ModuleType("transformers")
    dummy.pipeline = lambda *a, **k: (
        lambda text: [{"label": "POSITIVE", "score": 1.0}]
    )
    dummy.AutoTokenizer = types.SimpleNamespace(
        from_pretrained=lambda *a, **k: object()
    )
    dummy.AutoModelForSequenceClassification = types.SimpleNamespace(
        from_pretrained=lambda *a, **k: object()
    )
    sys.modules["transformers"] = dummy
    return importlib.reload(importlib.import_module("app.analytics"))


analytics = _load_analytics_with_stubbed_transformers()


def test_log_analysis_event_success(caplog):
    """Test case for test log analysis event success."""
    caplog.set_level("INFO")
    analytics.log_analysis_event(True, {"source": "test"})
    assert any(rec.message == "analytics.success" for rec in caplog.records)


def test_log_analysis_event_failure_with_details(caplog):
    """Test case for test log analysis event failure with details."""
    caplog.set_level("ERROR")
    analytics.log_analysis_event(False, {"source": "test"}, error="boom")
    assert any(
        rec.message == "analytics.failure" and getattr(rec, "error", "") == "boom"
        for rec in caplog.records
    )


def test_log_analysis_event_handles_missing_context(caplog):
    """Test case for test log analysis event handles missing context."""
    caplog.set_level("INFO")
    analytics.log_analysis_event(True, None, None)
    # Should not raise and may or may not emit a record; just ensure no exception.
    assert True


def test_merge_stats_combines_numbers_and_handles_none():
    """Test case for test merge stats combines numbers and handles none."""
    merged = analytics.merge_stats(
        {"views": 1, "likes": 2}, {"views": 2, "comments": 1}
    )
    assert merged["views"] == 3
    assert merged["likes"] == 2
    assert merged["comments"] == 1
    merged_none = analytics.merge_stats(None, {"views": 5})
    assert merged_none["views"] == 5
