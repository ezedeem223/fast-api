from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import analytics


def test_analyze_content_keyword_based_sentiment():
    result = analytics.analyze_content("This product is excellent and great")
    assert result["sentiment"]["sentiment"] == "POSITIVE"
    assert result["suggestion"]

    negative = analytics.analyze_content("This experience was terrible and bad")
    assert negative["sentiment"]["sentiment"] == "NEGATIVE"
    assert "post" in negative["suggestion"].lower()


def test_summarize_trends_counts_entries():
    entries = [
        SimpleNamespace(query="fastapi"),
        SimpleNamespace(query="fastapi"),
        SimpleNamespace(query="python"),
    ]
    summary = analytics.summarize_trends(entries)
    assert summary == {"fastapi": 2, "python": 1}


def test_record_search_query_creates_and_updates(monkeypatch):
    search_stat = SimpleNamespace(count=1, last_searched=None)

    query_existing = MagicMock()
    query_existing.filter.return_value.first.return_value = search_stat

    query_new = MagicMock()
    query_new.filter.return_value.first.return_value = None

    db = MagicMock()
    db.query.side_effect = [query_new, query_existing]

    analytics.record_search_query(db, "hello", 1)
    assert db.add.called

    analytics.record_search_query(db, "hello", 1)
    assert search_stat.count == 2
    assert db.commit.call_count == 2


def test_get_popular_and_recent_searches(monkeypatch):
    db = MagicMock()
    query = db.query.return_value
    query.order_by.return_value.limit.return_value.all.return_value = ["value"]

    assert analytics.get_popular_searches(db) == ["value"]
    assert analytics.get_recent_searches(db) == ["value"]


def test_get_user_searches(monkeypatch):
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = ["value"]
    assert analytics.get_user_searches(db, user_id=1) == ["value"]


def test_generate_search_trends_chart_json_fallback(monkeypatch):
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.group_by.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [SimpleNamespace(date="2024-01-01", count=5)]

    monkeypatch.setattr(analytics, "_PLOTTING_AVAILABLE", False)

    chart = analytics.generate_search_trends_chart(db=db, lookback_days=7)
    payload = json.loads(chart)
    assert payload["series"][0]["count"] == 5
