"""Additional coverage for Amenhotep router websocket paths."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, WebSocketDisconnect

from app import models
from app.routers import amenhotep as amenhotep_router


class FakeWebSocket:
    """Lightweight websocket stand-in with scripted receive_text."""

    def __init__(self, messages):
        self._messages = list(messages)
        self.sent = []
        self.close_calls = []
        self.client_state = SimpleNamespace(connected=False)
        self.app = SimpleNamespace(state=SimpleNamespace())

    async def accept(self):
        self.client_state.connected = True

    async def send_text(self, text):
        self.sent.append(text)

    async def receive_text(self):
        if not self._messages:
            raise WebSocketDisconnect()
        value = self._messages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def close(self, code=None, reason=None):
        self.close_calls.append({"code": code, "reason": reason})
        self.client_state.connected = False


class FakeDB:
    """Minimal DB stub for websocket handlers."""

    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_amenhotep_websocket_saves_and_responds(monkeypatch):
    """Websocket flow stores messages and returns AI response."""
    user = SimpleNamespace(id=1)

    class DummyBot:
        welcome_message = "welcome"

        async def get_response(self, user_id, message, db=None):
            return f"reply:{message}"

    async def fake_get_shared(app):
        return DummyBot()

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket(["hello", WebSocketDisconnect()])
    fake_db = FakeDB()

    await amenhotep_router.websocket_endpoint(
        ws, user_id=user.id, db=fake_db, current_user=user
    )

    assert ws.sent[0] == "welcome"
    assert "reply:hello" in ws.sent
    assert fake_db.added
    assert fake_db.added[0].response == "reply:hello"
    assert fake_db.commits >= 2


@pytest.mark.asyncio
async def test_amenhotep_websocket_empty_message_closes(monkeypatch):
    """Empty messages close the websocket with policy violation."""
    user = SimpleNamespace(id=2)

    class DummyBot:
        welcome_message = "welcome"

        async def get_response(self, user_id, message, db=None):
            return "ignored"

    async def fake_get_shared(app):
        return DummyBot()

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket([""])
    fake_db = FakeDB()

    await amenhotep_router.websocket_endpoint(
        ws, user_id=user.id, db=fake_db, current_user=user
    )

    assert ws.close_calls
    assert ws.close_calls[0]["code"] == 1003


@pytest.mark.asyncio
async def test_amenhotep_websocket_error_sends_message(monkeypatch):
    """Errors inside the loop send a friendly error message."""
    user = SimpleNamespace(id=3)

    class DummyBot:
        welcome_message = "welcome"

        async def get_response(self, user_id, message, db=None):
            raise RuntimeError("boom")

    async def fake_get_shared(app):
        return DummyBot()

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket(["boom", WebSocketDisconnect()])
    fake_db = FakeDB()

    await amenhotep_router.websocket_endpoint(
        ws, user_id=user.id, db=fake_db, current_user=user
    )

    assert ws.sent[-1].startswith(
        "Sorry, there was an error processing your message"
    )


@pytest.mark.asyncio
async def test_amenhotep_websocket_outer_error_closes(monkeypatch):
    """Failures during setup close the websocket with server error."""
    user = SimpleNamespace(id=4)

    async def fake_get_shared(app):
        raise RuntimeError("setup failed")

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket([])
    fake_db = FakeDB()

    await amenhotep_router.websocket_endpoint(
        ws, user_id=user.id, db=fake_db, current_user=user
    )

    assert ws.close_calls
    assert ws.close_calls[0]["code"] == 1011


@pytest.mark.asyncio
async def test_clear_chat_history_forbidden_returns_500(session):
    """Clear history wraps permission errors into 500 as implemented."""
    owner = models.User(
        email="owner@example.com", hashed_password="x", is_verified=True
    )
    other = models.User(
        email="other@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([owner, other])
    session.commit()
    session.refresh(owner)
    session.refresh(other)

    with pytest.raises(HTTPException) as exc:
        await amenhotep_router.clear_chat_history(
            user_id=owner.id, db=session, current_user=other
        )
    assert exc.value.status_code == 500
    assert (
        exc.value.detail == "An error occurred while clearing the chat history."
    )


@pytest.mark.asyncio
async def test_message_router_websocket_disconnect(monkeypatch):
    """MessageRouter handles normal websocket disconnects."""
    user = SimpleNamespace(id=5)

    class DummyBot:
        welcome_message = "welcome"

        async def get_response(self, user_id, message, db=None):
            return "reply"

    async def fake_get_shared(app):
        return DummyBot()

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket(["hi", WebSocketDisconnect()])
    fake_db = FakeDB()

    router = amenhotep_router.MessageRouter()
    await router.amenhotep_chat(ws, user_id=user.id, db=fake_db)

    assert ws.sent[0] == "welcome"
    assert ws.sent[1] == "reply"


@pytest.mark.asyncio
async def test_message_router_websocket_error_closes(monkeypatch):
    """MessageRouter closes when an unexpected error occurs."""
    user = SimpleNamespace(id=6)

    class DummyBot:
        welcome_message = "welcome"

        async def get_response(self, user_id, message, db=None):
            raise RuntimeError("fail")

    async def fake_get_shared(app):
        return DummyBot()

    monkeypatch.setattr(amenhotep_router, "get_shared_amenhotep", fake_get_shared)
    ws = FakeWebSocket(["boom"])
    fake_db = FakeDB()

    router = amenhotep_router.MessageRouter()
    await router.amenhotep_chat(ws, user_id=user.id, db=fake_db)

    assert ws.close_calls
    assert ws.close_calls[0]["code"] == 1011
