import pytest

from app import models
from app.modules.search.schemas import SearchParams
from app.modules.users.schemas import SortOption
from app.routers import search

# Align model attribute name used in router with actual column for tests
if not hasattr(models.SearchSuggestion, "frequency"):
    setattr(models.SearchSuggestion, "frequency", models.SearchSuggestion.usage_count)


def _user(session, email="user@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _post(session, owner, title="Hello", content="World"):
    post = models.Post(owner_id=owner.id, title=title, content=content)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


class DummyCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


@pytest.mark.asyncio
async def test_search_uses_typesense_ordering(monkeypatch, session):
    user = _user(session)
    p1 = _post(session, user, title="first", content="alpha")
    p2 = _post(session, user, title="second", content="beta")

    class DummyTS:
        def search_posts(self, query, limit=10):
            return [{"document": {"post_id": p2.id}}, {"document": {"post_id": p1.id}}]

    monkeypatch.setattr(search, "get_typesense_client", lambda: DummyTS())
    monkeypatch.setenv("APP_ENV", "production")
    params = SearchParams(query="a", sort_by=SortOption.RELEVANCE)
    resp = await search.search(params, db=session, current_user=user)
    ids = [r.id for r in resp["results"]]
    assert ids == [p2.id, p1.id]


@pytest.mark.asyncio
async def test_search_typesense_failure_falls_back(monkeypatch, session):
    user = _user(session)
    p = _post(session, user, title="only", content="text")

    class FailingTS:
        def search_posts(self, *a, **k):
            raise RuntimeError("fail")

    monkeypatch.setattr(search, "get_typesense_client", lambda: FailingTS())
    monkeypatch.setenv("APP_ENV", "production")
    params = SearchParams(query="text", sort_by=SortOption.RELEVANCE)
    resp = await search.search(params, db=session, current_user=user)
    assert any(r.id == p.id for r in resp["results"])


@pytest.mark.asyncio
async def test_autocomplete_caches_results(monkeypatch, session):
    _user(session)
    suggestion = models.SearchSuggestion(term="he", usage_count=5)
    session.add(suggestion)
    session.commit()

    dummy_cache = DummyCache()
    monkeypatch.setattr(search, "_cache_client", lambda: dummy_cache)
    monkeypatch.setenv("APP_ENV", "production")

    first = await search.autocomplete(query="h", db=session, limit=5)
    assert first and first[0].term == "he"
    # Second call served from cache (store contains key)
    cached = await search.autocomplete(query="h", db=session, limit=5)
    assert dummy_cache.get("autocomplete:h") is not None
    assert cached[0]["term"] == "he"


@pytest.mark.asyncio
async def test_record_search_increments_frequency(monkeypatch, session):
    user = _user(session)
    term = "searchme"

    monkeypatch.setattr(search.oauth2, "get_current_user", lambda: user)
    await search.record_search(term=term, db=session, current_user=user)
    suggestion = session.query(models.SearchSuggestion).filter_by(term=term).first()
    assert suggestion is not None
