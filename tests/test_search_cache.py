import fnmatch

import pytest

from app import models
from app.analytics import (
    get_popular_searches,
    get_user_searches,
    record_search_query,
)
from app.core.config import settings
from app.modules.search.cache import invalidate_stats_cache


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)

    def scan_iter(self, match=None):
        pattern = match or "*"
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, pattern):
                yield key


@pytest.fixture
def fake_redis():
    previous = settings.__class__.redis_client
    client = FakeRedis()
    settings.__class__.redis_client = client
    try:
        yield client
    finally:
        settings.__class__.redis_client = previous


def test_popular_searches_uses_cache(session, test_user, fake_redis):
    record_search_query(session, "redis caching", test_user["id"])
    results_first = get_popular_searches(session, limit=5)
    assert results_first
    assert results_first[0].query == "redis caching"

    # Mutate database without invalidating caches to ensure cached result is returned.
    stat = session.query(models.SearchStatistics).first()
    stat.count = 999
    session.commit()

    results_cached = get_popular_searches(session, limit=5)
    assert results_cached[0].count != 999


def test_user_searches_invalidation(session, test_user, fake_redis):
    record_search_query(session, "first", test_user["id"])
    initial = get_user_searches(session, test_user["id"], limit=5)
    assert initial and initial[0].query == "first"

    record_search_query(session, "second", test_user["id"])
    updated = get_user_searches(session, test_user["id"], limit=5)
    assert any(stat.query == "second" for stat in updated)

    # After manual invalidation, cache should be empty.
    invalidate_stats_cache(for_user_id=test_user["id"])
    final = get_user_searches(session, test_user["id"], limit=5)
    assert any(stat.query == "second" for stat in final)
