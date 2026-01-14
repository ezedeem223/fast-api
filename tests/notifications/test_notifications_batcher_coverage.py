"""Additional coverage for notification batching helpers."""

import pytest

from app.modules.notifications import batching as batching_module
from app.modules.notifications.batching import NotificationBatcher


@pytest.mark.asyncio
async def test_batcher_flush_and_digest(monkeypatch):
    sent = {"emails": [], "push": []}

    async def fake_send_email(message):
        sent["emails"].append(message)

    def fake_send_multicast(tokens, title, body, data=None):
        sent["push"].append({"tokens": tokens, "title": title, "body": body, "data": data})

    monkeypatch.setattr(batching_module, "send_email_notification", fake_send_email)
    monkeypatch.setattr(
        batching_module, "send_multicast_notification", fake_send_multicast
    )

    batcher = NotificationBatcher(
        max_batch_size=2,
        max_wait_time=0.0,
        digest_window_seconds=0.0,
        digest_max_size=2,
    )

    await batcher.add(
        {
            "channel": "email",
            "recipient": "a@example.com",
            "title": "Hello",
            "content": "Email body",
        }
    )
    await batcher.add(
        {
            "channel": "push",
            "tokens": ["t1"],
            "title": "Push title",
            "content": "Push body",
            "id": 12,
        }
    )

    await batcher.add(
        {
            "channel": "in_app",
            "recipient": "ignored@example.com",
            "title": "In app",
            "content": "In app body",
        }
    )
    await batcher.flush()

    assert sent["emails"]
    assert sent["push"]

    await batcher.add_digest(
        {"recipient": "digest@example.com", "title": "d1", "content": "c1"}
    )
    await batcher.add_digest(
        {"recipient": "digest@example.com", "title": "d2", "content": "c2"}
    )

    assert len(sent["emails"]) >= 2


def test_batcher_push_formatting_variants():
    single = NotificationBatcher._format_batch_push(
        [{"title": "Single", "content": "C"}]
    )
    assert single == "C"

    empty = NotificationBatcher._format_batch_push([{"title": None, "content": None}])
    assert "new notification" in empty.lower()

    multi = NotificationBatcher._format_batch_push(
        [
            {"title": "A"},
            {"title": "B"},
            {"title": "C"},
            {"title": "D"},
        ]
    )
    assert "..." in multi
