"""Additional coverage for analytics charting helpers."""
from __future__ import annotations

import base64
from datetime import date

import pytest

from app import analytics


class _FakeSeries:
    def __init__(self, data):
        self._data = data

    def to_list(self):
        return list(self._data)


class _FakeDataFrame:
    def __init__(self, data):
        self._data = data

    def sort(self, _):
        return self

    def __getitem__(self, key):
        return _FakeSeries(self._data[key])


def test_cached_stats_short_circuit(monkeypatch):
    """Use cached payloads for popular/recent searches."""
    payload = [
        {
            "query": "cached",
            "count": 3,
            "last_searched": "2025-01-01T00:00:00+00:00",
        }
    ]
    monkeypatch.setattr(analytics, "get_cached_json", lambda *_: payload)

    popular = analytics.get_popular_searches(db=object(), limit=3)
    recent = analytics.get_recent_searches(db=object(), limit=3)

    assert popular[0].query == "cached"
    assert recent[0].count == 3


def test_generate_search_trends_chart(monkeypatch):
    """Render chart using stubbed plotting stack."""
    class FakeRow:
        def __init__(self, dt, count):
            self.date = dt
            self.count = count

    class FakeQuery:
        def group_by(self, *_, **__):
            return self

        def order_by(self, *_, **__):
            return self

        def all(self):
            return [FakeRow(date(2025, 1, 1), 2)]

    class FakeDB:
        def query(self, *_, **__):
            return FakeQuery()

    monkeypatch.setattr(analytics, "get_db", lambda: iter([FakeDB()]))
    class DummyStats:
        last_searched = "last"
        updated_at = "updated_at"
        id = "id"

    monkeypatch.setattr(analytics, "SearchStatistics", DummyStats)
    monkeypatch.setattr(analytics, "pl", type("PL", (), {"DataFrame": _FakeDataFrame}))

    class FakePlt:
        def figure(self, *_, **__):
            return None

        def title(self, *_):
            return None

        def xlabel(self, *_):
            return None

        def ylabel(self, *_):
            return None

        def xticks(self, *_, **__):
            return None

        def tight_layout(self):
            return None

        def savefig(self, buffer, format=None):
            buffer.write(b"png")

    monkeypatch.setattr(analytics, "plt", FakePlt())
    monkeypatch.setattr(analytics, "sns", type("SNS", (), {"lineplot": lambda *_, **__: None}))

    encoded = analytics.generate_search_trends_chart()
    assert base64.b64decode(encoded) == b"png"


def test_polars_merge_stats():
    """Validate merge behavior for empty and populated stats."""
    class FakeAgg:
        def __init__(self, data):
            self._data = data

        def to_dict(self, *_):
            return self._data

    class FakeGroup:
        def __init__(self, data):
            self._data = data

        def agg(self, *_):
            return FakeAgg(self._data)

    class FakeFrame:
        def __init__(self, data):
            self._data = data

        def group_by(self, *_):
            keys = self._data["key"]
            values = self._data["value"]
            totals = {}
            for key, value in zip(keys, values):
                totals[key] = totals.get(key, 0) + value
            return FakeGroup({"key": list(totals.keys()), "value": list(totals.values())})

    monkeypatch = pytest.MonkeyPatch()
    class FakeCol:
        def sum(self):
            return None

    monkeypatch.setattr(
        analytics,
        "pl",
        type("PL", (), {"DataFrame": FakeFrame, "col": lambda *_: FakeCol()}),
    )

    assert analytics.polars_merge_stats(None, {"a": 1}) == {"a": 1}
    assert analytics.polars_merge_stats({"a": 2}, None) == {"a": 2}
    merged = analytics.polars_merge_stats({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert merged["a"] == 1
    assert merged["b"] == 5
    assert merged["c"] == 4
    monkeypatch.undo()
