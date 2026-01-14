"""Test module for test call signaling."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import call_signaling
from fastapi import WebSocketDisconnect, status


class FakeWebSocket:
    """Test class for FakeWebSocket."""
    def __init__(self, messages):
        self._messages = list(messages)
        self.accept = AsyncMock()
        self.close = AsyncMock()
        self.sent = []

    async def receive_json(self):
        if not self._messages:
            raise WebSocketDisconnect()
        value = self._messages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def send_json(self, payload):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_join_denied_without_token(monkeypatch):
    """Test case for test join denied without token."""
    registry = call_signaling.CallRoomRegistry(default_ttl=60)
    monkeypatch.setattr(call_signaling, "room_registry", registry)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", AsyncMock())

    # Pre-create a room owned by user 1; allow only user 2
    await registry.create_room("room1", owner_id=1, allowed_participants={2})

    ws = FakeWebSocket([])
    user3 = SimpleNamespace(id=3)

    await call_signaling.signaling_ws(ws, "room1", current_user=user3, join_token=None)
    ws.close.assert_awaited()


@pytest.mark.asyncio
async def test_room_expiry_blocks_join(monkeypatch):
    """Test case for test room expiry blocks join."""
    registry = call_signaling.CallRoomRegistry(default_ttl=1)
    monkeypatch.setattr(call_signaling, "room_registry", registry)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", AsyncMock())

    await registry.create_room("expire", owner_id=1, allowed_participants=set(), ttl=-1)
    ws = FakeWebSocket([])
    owner = SimpleNamespace(id=1)

    await call_signaling.signaling_ws(ws, "expire", current_user=owner, join_token=None)
    ws.close.assert_awaited()
    assert "room expired" in ws.close.call_args.kwargs.get("reason", "")


@pytest.mark.asyncio
async def test_join_token_single_use(monkeypatch):
    """Test case for test join token single use."""
    registry = call_signaling.CallRoomRegistry(default_ttl=120)
    monkeypatch.setattr(call_signaling, "room_registry", registry)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", AsyncMock())

    await registry.create_room("room2", owner_id=1)
    token = await registry.issue_join_token("room2", owner_id=1, allowed_user_id=2)

    # First join succeeds
    ws1 = FakeWebSocket([{"type": "offer"}])
    user2 = SimpleNamespace(id=2)
    await call_signaling.signaling_ws(
        ws1, "room2", current_user=user2, join_token=token
    )
    assert ws1.close.await_count == 0

    # Replay with same token should be denied
    ws2 = FakeWebSocket([])
    await call_signaling.signaling_ws(
        ws2, "room2", current_user=user2, join_token=token
    )
    ws2.close.assert_awaited()


@pytest.mark.asyncio
async def test_signaling_failure_closes_and_cleans_up(monkeypatch):
    """Test case for test signaling failure closes and cleans up."""
    registry = call_signaling.CallRoomRegistry(default_ttl=120)
    monkeypatch.setattr(call_signaling, "room_registry", registry)

    async def fail_send(payload, uid):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.notifications.manager.send_personal_message",
        fail_send,
    )

    state = await registry.create_room("room3", owner_id=1)
    state.participants.add(2)  # ensure there is another participant to broadcast to
    ws = FakeWebSocket([{"type": "offer"}])
    user1 = SimpleNamespace(id=1)

    await call_signaling.signaling_ws(ws, "room3", current_user=user1, join_token=None)
    ws.close.assert_awaited()
    assert ws.close.call_args.kwargs.get("code") == status.WS_1011_INTERNAL_ERROR
    participants = await registry.participants("room3")
    assert 1 not in participants
