"""Test module for test websocket auth session5."""
import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api import websocket as ws_module
from app.core.config import settings
from app.notifications import manager as notifications_manager
from fastapi import status


class DummyWebSocket:
    """Test class for DummyWebSocket."""
    def __init__(self):
        self.closed_with = None
        self.received = asyncio.Queue()
        self.close_calls = []

    async def accept(self):
        return True

    async def receive_text(self):
        return await self.received.get()

    async def send_text(self, data):
        return data

    async def close(self, code: int, reason: str):
        self.closed_with = (code, reason)
        self.close_calls.append((code, reason))


@pytest.fixture(autouse=True)
def force_test_env(monkeypatch):
    """Pytest fixture for force_test_env."""
    monkeypatch.setattr(settings, "environment", "test")
    yield


def test_auth_missing_token_prod_rejects(monkeypatch):
    """Test case for test auth missing token prod rejects."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_websocket_auth_requires_token_prod")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FORCE_HTTPS", "true")
    # Ensure TrustedHost path isn't triggered by existing allowed_hosts.
    monkeypatch.setattr(settings, "allowed_hosts", ["example.com"])
    ws = DummyWebSocket()
    token = None
    user = asyncio.run(
        ws_module._authenticate_websocket(ws, claimed_user_id=1, token=token)
    )
    assert user is None
    assert ws.closed_with[0] == 4401


def test_auth_missing_token_allowed_in_test(monkeypatch):
    """Test case for test auth missing token allowed in test."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    ws = DummyWebSocket()
    user = asyncio.run(
        ws_module._authenticate_websocket(ws, claimed_user_id=42, token=None)
    )
    assert user == 42


def test_auth_user_mismatch_closes(monkeypatch):
    """Test case for test auth user mismatch closes."""
    ws = DummyWebSocket()

    class TokenData:
        def __init__(self, id):
            self.id = id

    def fake_verify(token, exc):
        return TokenData(id=99)

    monkeypatch.setattr(ws_module.oauth2, "verify_access_token", fake_verify)
    user = asyncio.run(
        ws_module._authenticate_websocket(ws, claimed_user_id=1, token="t")
    )
    assert user is None
    assert ws.closed_with[0] == status.WS_1008_POLICY_VIOLATION


def test_auth_invalid_token_closes(monkeypatch):
    """Test case for test auth invalid token closes."""
    ws = DummyWebSocket()

    def fake_verify(token, exc):
        raise exc

    monkeypatch.setattr(ws_module.oauth2, "verify_access_token", fake_verify)
    user = asyncio.run(
        ws_module._authenticate_websocket(ws, claimed_user_id=1, token="bad")
    )
    assert user is None
    assert ws.closed_with[0] == 4401


def test_websocket_endpoint_disconnect_on_empty(monkeypatch):
    """Test case for test websocket endpoint disconnect on empty."""
    ws = DummyWebSocket()
    # enqueue empty message then stop
    ws.received.put_nowait("")

    connect_calls = []
    disconnect_calls = []

    async def fake_connect(sock, user_id):
        connect_calls.append((sock, user_id))
        return True

    async def fake_disconnect(sock, user_id, reason=None):
        disconnect_calls.append((user_id, reason))

    monkeypatch.setattr(notifications_manager, "connect", fake_connect)
    monkeypatch.setattr(notifications_manager, "disconnect", fake_disconnect)
    monkeypatch.setattr(ws_module, "send_real_time_notification", lambda *a, **k: None)

    # Bypass auth
    async def fake_auth(*args, **kwargs):
        return 7

    monkeypatch.setattr(ws_module, "_authenticate_websocket", fake_auth)

    asyncio.run(ws_module.websocket_endpoint(ws, user_id=7, token=None))
    assert connect_calls == [(ws, 7)]
    assert disconnect_calls == [(7, "empty_message")]


def test_websocket_endpoint_handles_disconnect_exception(monkeypatch):
    """Test case for test websocket endpoint handles disconnect exception."""
    ws = DummyWebSocket()
    ws.received.put_nowait("hi")

    async def fake_receive():
        raise WebSocketDisconnect(code=1000)

    ws.receive_text = fake_receive  # type: ignore[assignment]

    disconnect_calls = []

    async def fake_disconnect(sock, user_id, reason=None):
        disconnect_calls.append((user_id, reason))

    async def fake_connect(*args, **kwargs):
        return True

    monkeypatch.setattr(notifications_manager, "connect", fake_connect)
    monkeypatch.setattr(notifications_manager, "disconnect", fake_disconnect)
    monkeypatch.setattr(ws_module, "send_real_time_notification", lambda *a, **k: None)

    async def fake_auth(*args, **kwargs):
        return 5

    monkeypatch.setattr(ws_module, "_authenticate_websocket", fake_auth)

    asyncio.run(ws_module.websocket_endpoint(ws, user_id=5, token=None))
    assert disconnect_calls == [(5, "disconnect:1000")]
