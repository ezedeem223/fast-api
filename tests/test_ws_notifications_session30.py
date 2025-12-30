from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from app import notifications as notifications_module
from app.api import websocket as ws_module
from app.core.app_factory import create_app
from app.core.config import settings
from app.modules.notifications import service as notification_service
from app.routers import notifications as notifications_router
from fastapi import status
from tests.testclient import TestClient


class QueueWebSocket:
    """Lightweight test double for WebSocket receive/send/close."""

    def __init__(self, messages):
        self._messages = list(messages)
        self.close_calls = []

    async def accept(self):
        return True

    async def receive_text(self):
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect(code=1000)

    async def close(self, code: int, reason: str = ""):
        self.close_calls.append((code, reason))


@pytest.mark.asyncio
async def test_websocket_sends_and_disconnects_on_empty(monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    sent = []
    disconnects = []
    connects = []
    ws = QueueWebSocket(["ping", ""])

    async def fake_connect(sock, user_id):
        connects.append((sock, user_id))
        return True

    async def fake_disconnect(sock, user_id, reason=None):
        disconnects.append((user_id, reason))

    async def fake_send(user_id, msg):
        sent.append((user_id, msg))

    async def fake_auth(*args, **kwargs):
        return 9

    monkeypatch.setattr(
        ws_module,
        "manager",
        SimpleNamespace(connect=fake_connect, disconnect=fake_disconnect),
    )
    monkeypatch.setattr(ws_module, "send_real_time_notification", fake_send)
    monkeypatch.setattr(ws_module, "_authenticate_websocket", fake_auth)

    await ws_module.websocket_endpoint(ws, user_id=9, token=None)

    assert sent == [(9, "ping")]
    assert disconnects == [(9, "empty_message")]
    assert connects == [(ws, 9)]


@pytest.mark.asyncio
async def test_websocket_exception_path_closes_and_disconnects(monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    ws = QueueWebSocket([])

    async def raise_error():
        raise RuntimeError("boom")

    ws.receive_text = raise_error  # type: ignore[assignment]

    disconnects = []
    closes = []

    async def fake_connect(*args, **kwargs):
        return True

    async def fake_disconnect(sock, user_id, reason=None):
        disconnects.append((user_id, reason))

    async def fake_close(code: int, reason: str = ""):
        closes.append((code, reason))

    ws.close = fake_close  # type: ignore[assignment]

    async def fake_auth(*args, **kwargs):
        return 4

    monkeypatch.setattr(
        ws_module,
        "manager",
        SimpleNamespace(connect=fake_connect, disconnect=fake_disconnect),
    )
    monkeypatch.setattr(ws_module, "send_real_time_notification", lambda *a, **k: None)
    monkeypatch.setattr(ws_module, "_authenticate_websocket", fake_auth)

    await ws_module.websocket_endpoint(ws, user_id=4, token=None)

    assert disconnects == [(4, "error")]
    assert closes == [(status.WS_1011_INTERNAL_ERROR, "")]


@pytest.mark.asyncio
async def test_send_real_time_notification_wraps_string(monkeypatch):
    sent = []

    async def fake_send(payload, user_id):
        sent.append((payload, user_id))

    monkeypatch.setattr(
        notifications_module.manager, "send_personal_message", fake_send
    )

    await notifications_module.send_real_time_notification(7, "hello-world")

    assert sent == [({"message": "hello-world", "type": "simple_notification"}, 7)]


def test_publish_realtime_broadcast_uses_redis(monkeypatch):
    published = []

    class FakeClient:
        def publish(self, channel, payload):
            published.append((channel, payload))

    class FakeRedis:
        def from_url(self, url):
            assert url == "redis://example"
            return FakeClient()

    monkeypatch.setattr(notification_service, "redis", FakeRedis())
    monkeypatch.setattr(notification_service, "_redis_client", None)
    monkeypatch.setenv("REALTIME_REDIS_URL", "redis://example")
    monkeypatch.delenv("REALTIME_REDIS_CHANNEL", raising=False)

    notification_service._publish_realtime_broadcast({"msg": "ok"})

    assert published[0][0] == "realtime:broadcast"
    assert '"msg": "ok"' in published[0][1]


def test_publish_realtime_broadcast_handles_redis_failure(monkeypatch):
    class FailingRedis:
        def from_url(self, url):
            raise RuntimeError("no redis")

    monkeypatch.setattr(notification_service, "redis", FailingRedis())
    monkeypatch.setattr(notification_service, "_redis_client", None)
    monkeypatch.setenv("REALTIME_REDIS_URL", "redis://fail")

    # Should not raise even when redis is unavailable.
    notification_service._publish_realtime_broadcast({"msg": "skip"})

    assert notification_service._redis_client is False


def test_notifications_subscribe_missing_and_duplicate(monkeypatch):
    app = create_app()
    user = SimpleNamespace(id=11)
    # reset registry
    notifications_router._subscriptions_registry.clear()
    app.dependency_overrides[notifications_router.oauth2.get_current_user] = (
        lambda: user
    )
    client = TestClient(app)

    missing = client.post("/notifications/subscribe")
    assert missing.status_code == 400

    first = client.post("/notifications/subscribe", params={"token": "abc"})
    assert first.status_code == 200
    assert notifications_router._subscriptions_registry[user.id] == "abc"

    dup = client.post("/notifications/subscribe", params={"token": "abc"})
    assert dup.status_code == 200
    assert dup.json()["status"] == "already_subscribed"
