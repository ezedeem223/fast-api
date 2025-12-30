from types import SimpleNamespace

from app.modules.search import cache as search_cache
from app.modules.utils import search as utils_search


def test_cache_get_set_delete(monkeypatch):
    store = {}

    class DummyClient:
        def get(self, key):
            return store.get(key)

        def setex(self, key, ttl, value):
            store[key] = value

        def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

    dummy = DummyClient()
    monkeypatch.setattr(search_cache, "_client", lambda: dummy)

    assert search_cache.get_cached_json("missing") is None
    search_cache.set_cached_json("k", {"x": 1})
    # value stored is JSON string; get_cached_json should load it
    assert search_cache.get_cached_json("k") == {"x": 1}

    search_cache.delete_keys(["k"])
    assert search_cache.get_cached_json("k") is None


def test_cache_delete_pattern(monkeypatch):
    store = {"a:1": "1", "a:2": "2", "b:1": "3"}

    class DummyIter(str):
        def __iter__(self):
            return iter([])

    class DummyClient:
        def scan_iter(self, match=None):
            return [
                k
                for k in store
                if match is None or k.startswith(match.replace("*", ""))
            ]

        def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

    dummy = DummyClient()
    monkeypatch.setattr(search_cache, "_client", lambda: dummy)
    search_cache.delete_pattern("a:*")
    assert "a:1" not in store and "a:2" not in store and "b:1" in store


def test_cache_key_helpers_and_invalidation(monkeypatch):
    deleted = []

    class DummyClient:
        def scan_iter(self, match=None):
            return [match.replace("*", "1")]

        def delete(self, *keys):
            deleted.extend(keys)

    dummy = DummyClient()
    monkeypatch.setattr(search_cache, "_client", lambda: dummy)
    search_cache.invalidate_stats_cache(for_user_id=5)
    assert "search:stats:user:5:1" in deleted
    assert "search:stats:popular:1" in deleted
    assert "search:stats:recent:1" in deleted


def test_get_spell_suggestions_filters_tokens(monkeypatch):
    class DummySpell:
        def __contains__(self, item):
            return item == "hello"

        def correction(self, word):
            return "world"

    monkeypatch.setattr(utils_search, "spell", DummySpell())
    assert utils_search.get_spell_suggestions("hello 123 ?") == ["hello"]
    assert utils_search.get_spell_suggestions("helo") == ["world"]


def test_format_spell_suggestions_differs():
    assert utils_search.format_spell_suggestions(
        "helo wrld", ["hello", "world"]
    ).startswith("Did you mean")
    assert (
        utils_search.format_spell_suggestions("hello world", ["hello", "world"]) == ""
    )


def test_sort_search_results_sqlite(monkeypatch):
    # Build a fake query with minimal attributes
    class DummyQuery:
        def __init__(self):
            self.session = SimpleNamespace(
                bind=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
            )
            self.ordered_by = None

        def order_by(self, expr):
            self.ordered_by = expr
            return self

    q = DummyQuery()
    sorted_q = utils_search.sort_search_results(q, "RELEVANCE", search_text="foo")
    assert sorted_q.ordered_by is not None


def test_sort_search_results_defaults():
    class DummyQuery:
        def __init__(self):
            self.session = None
            self.ordered_by = None

        def order_by(self, expr):
            self.ordered_by = expr
            return self

    q = DummyQuery()
    assert (
        utils_search.sort_search_results(q, "DATE_DESC", search_text="x").ordered_by
        is not None
    )
    assert (
        utils_search.sort_search_results(q, "DATE_ASC", search_text="x").ordered_by
        is not None
    )
    assert (
        utils_search.sort_search_results(q, "POPULARITY", search_text="x").ordered_by
        is not None
    )
    assert utils_search.sort_search_results(q, "UNKNOWN", search_text="x") is q
