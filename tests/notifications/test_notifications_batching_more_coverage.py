"""Additional coverage for notification batching helpers."""
from __future__ import annotations

import pytest

from app.modules.notifications import batching


@pytest.mark.asyncio
async def test_batcher_digest_and_flush_empty(monkeypatch):
    """Cover digest guard clauses and empty flush handling."""
    batcher = batching.NotificationBatcher()

    await batcher.add_digest({"title": "no recipient"})
    await batcher.flush()
    assert batcher.batch == []
    assert batcher._digest_batches == {}


@pytest.mark.asyncio
async def test_batcher_push_and_formatting(monkeypatch):
    """Exercise push grouping, token filtering, and formatting branches."""
    batcher = batching.NotificationBatcher()

    sent = []

    def fake_send(tokens, title, body, data=None):
        sent.append((tokens, title, body, data))

    monkeypatch.setattr(batching, "send_multicast_notification", fake_send)

    notifications = [
        {"channel": "push", "device_tokens": [], "content": "skip"},
        {"channel": "push", "tokens": ["t1", "t2"], "title": "Title", "id": 1},
        {"channel": "push", "tokens": ["t1", "t2"], "content": "Second", "id": 2},
    ]

    await batcher._send_batch_push(notifications)
    assert sent

    single = batching.NotificationBatcher._format_batch_push(
        [{"content": "Hello"}]
    )
    assert single == "Hello"

    no_titles = batching.NotificationBatcher._format_batch_push(
        [{"content": ""}, {}]
    )
    assert "You have" in no_titles

    many_titles = batching.NotificationBatcher._format_batch_push(
        [
            {"title": "a"},
            {"title": "b"},
            {"title": "c"},
            {"title": "d"},
        ]
    )
    assert many_titles.endswith("...")


@pytest.mark.asyncio
async def test_batcher_in_app_placeholder():
    """Cover in-app placeholder branch."""
    batcher = batching.NotificationBatcher()
    result = await batcher._send_batch_in_app([{"channel": "in_app"}])
    assert result is None
