import asyncio

import pytest

from app.cache import cache


@pytest.mark.asyncio
async def test_cache_reuses_results(monkeypatch):
    call_count = {"calls": 0}

    @cache(expire=60)
    async def sample(value):
        call_count["calls"] += 1
        await asyncio.sleep(0)
        return value * 2

    assert await sample(3) == 6
    assert await sample(3) == 6
    assert call_count["calls"] == 1


@pytest.mark.asyncio
async def test_cache_isolated_per_function():
    first_hits = {"calls": 0}
    second_hits = {"calls": 0}

    @cache(expire=60)
    async def first(value):
        first_hits["calls"] += 1
        return value + 1

    @cache(expire=60)
    async def second(value):
        second_hits["calls"] += 1
        return value + 2

    assert await first(1) == 2
    assert await second(1) == 3
    assert await first(1) == 2
    assert await second(1) == 3
    assert first_hits["calls"] == 1
    assert second_hits["calls"] == 1
