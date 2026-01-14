"""Additional coverage for call router websocket and helpers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect, status

from app.routers import call as call_router


class FakeQuery:
    """Simple query stub returning a fixed result."""

    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class FakeDB:
    """Minimal DB stub for call router tests."""

    def __init__(self, result=None):
        self._result = result
        self.commits = 0

    def query(self, model):
        return FakeQuery(self._result)

    def commit(self):
        self.commits += 1


class FakeWebSocket:
    """WebSocket stand-in with scripted receive_json."""

    def __init__(self, messages):
        self._messages = list(messages)
        self.close_calls = []

    async def accept(self):
        return None

    async def receive_json(self):
        if not self._messages:
            raise WebSocketDisconnect()
        value = self._messages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def close(self, code=None, reason=None):
        self.close_calls.append({"code": code, "reason": reason})


@pytest.mark.asyncio
async def test_call_websocket_rejects_nonparticipant(monkeypatch):
    """Non-participants are rejected with policy violation."""
    call = SimpleNamespace(id=1, caller_id=1, receiver_id=2)
    db = FakeDB(result=call)
    ws = FakeWebSocket([])

    connect_mock = AsyncMock()
    monkeypatch.setattr(call_router.manager, "connect", connect_mock)
    monkeypatch.setattr(call_router.manager, "disconnect", AsyncMock())

    current_user = SimpleNamespace(id=3)
    await call_router.websocket_endpoint(ws, call_id=1, db=db, current_user=current_user)

    assert ws.close_calls[0]["code"] == status.WS_1008_POLICY_VIOLATION
    connect_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_websocket_connect_false_disconnects(monkeypatch):
    """If manager.connect returns False, the handler exits early."""
    call = SimpleNamespace(id=2, caller_id=1, receiver_id=2)
    db = FakeDB(result=call)
    ws = FakeWebSocket([RuntimeError("receive_json should not run")])

    monkeypatch.setattr(call_router.manager, "connect", AsyncMock(return_value=False))
    disconnect_mock = AsyncMock()
    monkeypatch.setattr(call_router.manager, "disconnect", disconnect_mock)

    current_user = SimpleNamespace(id=1)
    await call_router.websocket_endpoint(ws, call_id=2, db=db, current_user=current_user)

    disconnect_mock.assert_awaited()
    assert ws.close_calls == []


@pytest.mark.asyncio
async def test_call_websocket_disconnect_flow_calls_handlers(monkeypatch):
    """WebSocket disconnect triggers cleanup and helper calls."""
    call = SimpleNamespace(id=3, caller_id=1, receiver_id=2)
    db = FakeDB(result=call)
    ws = FakeWebSocket([{"type": "offer"}, WebSocketDisconnect()])

    monkeypatch.setattr(call_router.manager, "connect", AsyncMock(return_value=True))
    disconnect_mock = AsyncMock()
    monkeypatch.setattr(call_router.manager, "disconnect", disconnect_mock)

    enc_mock = AsyncMock()
    quality_mock = AsyncMock()
    data_mock = AsyncMock()
    disconnect_call_mock = AsyncMock()
    monkeypatch.setattr(call_router, "_handle_encryption_key_update", enc_mock)
    monkeypatch.setattr(call_router, "_handle_call_quality", quality_mock)
    monkeypatch.setattr(call_router, "_handle_call_data", data_mock)
    monkeypatch.setattr(call_router, "_handle_call_disconnect", disconnect_call_mock)

    cleaned = {"called": False}

    def fake_clean():
        cleaned["called"] = True

    monkeypatch.setattr(call_router, "clean_old_quality_buffers", fake_clean)

    current_user = SimpleNamespace(id=1)
    await call_router.websocket_endpoint(ws, call_id=3, db=db, current_user=current_user)

    enc_mock.assert_awaited()
    quality_mock.assert_awaited()
    data_mock.assert_awaited()
    disconnect_call_mock.assert_awaited()
    assert cleaned["called"] is True
    disconnect_mock.assert_awaited()


@pytest.mark.asyncio
async def test_call_websocket_exception_closes(monkeypatch):
    """Unexpected exceptions close the websocket with server error."""
    call = SimpleNamespace(id=4, caller_id=1, receiver_id=2)
    db = FakeDB(result=call)
    ws = FakeWebSocket([RuntimeError("boom")])

    monkeypatch.setattr(call_router.manager, "connect", AsyncMock(return_value=True))
    monkeypatch.setattr(call_router.manager, "disconnect", AsyncMock())

    current_user = SimpleNamespace(id=1)
    await call_router.websocket_endpoint(ws, call_id=4, db=db, current_user=current_user)

    assert ws.close_calls[0]["code"] == 1011


def test_update_call_quality_invokes_service(monkeypatch):
    """update_call_quality delegates to CallService."""

    class DummyService:
        def __init__(self, db):
            self.db = db
            self.seen = []

        def update_call_quality(self, call_id, quality_score):
            self.seen.append((call_id, quality_score))

    dummy = DummyService(db=object())

    def fake_service(db):
        return dummy

    monkeypatch.setattr(call_router, "CallService", fake_service)
    call_router.update_call_quality(db=object(), call_id=9, quality_score=4)
    assert dummy.seen == [(9, 4)]


@pytest.mark.asyncio
async def test_handle_encryption_key_update_rotates_and_sends(monkeypatch):
    """Encryption key updates trigger payloads for both users."""
    old_time = datetime.now(timezone.utc) - call_router.KEY_UPDATE_INTERVAL - timedelta(
        seconds=1
    )
    call = SimpleNamespace(
        caller_id=1,
        receiver_id=2,
        encryption_key="old",
        last_key_update=old_time,
    )
    db = FakeDB()

    monkeypatch.setattr(call_router, "update_encryption_key", lambda _: "new")
    send_mock = AsyncMock()
    monkeypatch.setattr(call_router, "_send_call_payload", send_mock)

    await call_router._handle_encryption_key_update(call, db, other_user_id=2)

    assert call.encryption_key == "new"
    assert call.last_key_update > old_time
    assert db.commits == 1
    assert send_mock.await_count == 2


@pytest.mark.asyncio
async def test_handle_call_quality_schedules_update_and_adjusts(monkeypatch):
    """Quality updates schedule tasks and send recommendations."""
    call = SimpleNamespace(id=11, quality_score=1)
    db = FakeDB(result=call)
    added = []

    class FakeBackground:
        def add_task(self, func, *args):
            added.append((func, args))

    monkeypatch.setattr(call_router, "check_call_quality", lambda data, call_id: 5)
    monkeypatch.setattr(call_router, "should_adjust_video_quality", lambda call_id: True)
    monkeypatch.setattr(
        call_router, "get_recommended_video_quality", lambda call_id: "720p"
    )
    send_mock = AsyncMock()
    monkeypatch.setattr(call_router, "_send_call_payload", send_mock)

    await call_router._handle_call_quality(
        data={"quality": 5},
        call_id=11,
        db=db,
        current_user_id=1,
        other_user_id=2,
        background_tasks=FakeBackground(),
    )

    assert added
    assert added[0][0] is call_router.update_call_quality
    assert added[0][1] == (db, 11, 5)
    assert send_mock.await_count == 2


@pytest.mark.asyncio
async def test_send_call_payload_prefers_manager(monkeypatch):
    """Active connections use manager; otherwise fall back to notifications."""
    monkeypatch.setattr(call_router.manager, "active_connections", {7: True})
    send_mock = AsyncMock()
    monkeypatch.setattr(call_router.manager, "send_personal_message", send_mock)

    await call_router._send_call_payload(7, {"type": "offer"})
    send_mock.assert_awaited()

    fallback = SimpleNamespace(send_real_time_notification=AsyncMock())
    monkeypatch.setattr(call_router.manager, "active_connections", {})
    await call_router._send_call_payload(8, {"type": "offer"}, fallback)
    fallback.send_real_time_notification.assert_awaited_once()


def test_clean_quality_buffers_periodically(monkeypatch):
    """Periodic cleanup forwards to clean_old_quality_buffers."""
    called = {"ok": False}

    def fake_clean():
        called["ok"] = True

    monkeypatch.setattr(call_router, "clean_old_quality_buffers", fake_clean)
    call_router.clean_quality_buffers_periodically.__wrapped__()
    assert called["ok"] is True
