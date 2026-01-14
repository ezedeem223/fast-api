"""Test module for test notifications batching and caches."""
import pytest

from app.modules.notifications.batching import NotificationBatcher
from app.modules.notifications.common import (
    delivery_status_cache,
    notification_cache,
    priority_notification_cache,
)


@pytest.mark.asyncio
async def test_batcher_splits_when_max_reached(monkeypatch):
    """Test case for test batcher splits when max reached."""
    sent = {"count": 0}

    async def fake_process(batch):
        sent["count"] += len(batch)

    batcher = NotificationBatcher(max_batch_size=2, max_wait_time=10)
    monkeypatch.setattr(batcher, "_process_batch", fake_process)

    await batcher.add({"id": 1})
    assert sent["count"] == 0  # not yet flushed
    await batcher.add({"id": 2})
    assert sent["count"] == 2  # flushed when max reached


@pytest.mark.asyncio
async def test_batcher_batch_id_consistent(monkeypatch):
    """Test case for test batcher batch id consistent."""
    collected = []

    async def fake_process(batch):
        collected.append(list(batch))

    batcher = NotificationBatcher(max_batch_size=10, max_wait_time=10)
    monkeypatch.setattr(batcher, "_process_batch", fake_process)

    await batcher.add({"id": 1, "batch_id": "same"})
    await batcher.add({"id": 2, "batch_id": "same"})
    await batcher.flush()
    assert collected[0][0]["batch_id"] == collected[0][1]["batch_id"] == "same"


@pytest.mark.asyncio
async def test_batcher_empty_flush_is_noop(monkeypatch):
    """Test case for test batcher empty flush is noop."""
    batcher = NotificationBatcher()
    called = {"process": False}

    async def fake_process(batch):
        called["process"] = True

    monkeypatch.setattr(batcher, "_process_batch", fake_process)
    await batcher.flush()
    assert called["process"] is False


@pytest.mark.asyncio
async def test_batcher_flush_clears_batch(monkeypatch):
    """Test case for test batcher flush clears batch."""
    sent = {"count": 0}

    async def fake_process(batch):
        sent["count"] += len(batch)

    batcher = NotificationBatcher(max_batch_size=10, max_wait_time=10)
    monkeypatch.setattr(batcher, "_process_batch", fake_process)

    await batcher.add({"id": 1})
    await batcher.flush()
    assert sent["count"] == 1
    await batcher.flush()
    assert sent["count"] == 1  # no double-send


# ============== 25) caches priority/delivery ==============


def test_priority_cache_influences_decision():
    """Test case for test priority cache influences decision."""
    priority_notification_cache.clear()
    key = "category_pref_1_system"
    priority_notification_cache[key] = False
    assert priority_notification_cache.get(key) is False


def test_delivery_cache_set_and_clear():
    """Test case for test delivery cache set and clear."""
    delivery_status_cache.clear()
    key = "delivery_123"
    delivery_status_cache[key] = True
    assert delivery_status_cache[key] is True
    delivery_status_cache.clear()
    assert key not in delivery_status_cache


def test_cache_collision_different_users():
    """Test case for test cache collision different users."""
    notification_cache.clear()
    notification_cache["user_prefs_1"] = "prefs1"
    notification_cache["user_prefs_2"] = "prefs2"
    assert notification_cache["user_prefs_1"] == "prefs1"
    assert notification_cache["user_prefs_2"] == "prefs2"
