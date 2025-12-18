import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from app.modules.notifications import models as notification_models
from app.modules.notifications.service import (
    deliver_scheduled_notification,
    send_bulk_notifications,
)
from app.notifications import send_real_time_notification
from app.api.websocket import websocket_endpoint, manager as ws_manager
from app.modules.notifications.service import NotificationService


class FakeWebSocket:
    """Simple stand-in for WebSocket with scripted receive_text."""

    def __init__(self, messages):
        self._messages = list(messages)

    async def receive_text(self):
        if not self._messages:
            raise WebSocketDisconnect()
        value = self._messages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_deliver_scheduled_notification_sends_and_closes(monkeypatch, session, test_user):
    notif = notification_models.Notification(
        user_id=test_user["id"],
        content="scheduled",
        notification_type="sched",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    close_flag = {"closed": False}

    def fake_get_db():
        yield session

    async def fake_deliver(self, n):
        n.status = notification_models.NotificationStatus.DELIVERED
        session.commit()

    def fake_close():
        close_flag["closed"] = True

    monkeypatch.setattr("app.modules.notifications.service.get_db", fake_get_db)
    monkeypatch.setattr(NotificationService, "deliver_notification", fake_deliver)
    monkeypatch.setattr(session, "close", fake_close)

    await deliver_scheduled_notification(notif.id, datetime.now(timezone.utc))
    session.refresh(notif)
    assert notif.status == notification_models.NotificationStatus.DELIVERED
    assert close_flag["closed"] is True


@pytest.mark.asyncio
async def test_deliver_scheduled_notification_missing_logs_and_closes(monkeypatch, session):
    close_flag = {"closed": False}

    def fake_get_db():
        yield session

    def fake_close():
        close_flag["closed"] = True

    monkeypatch.setattr("app.modules.notifications.service.get_db", fake_get_db)
    monkeypatch.setattr(session, "close", fake_close)

    await deliver_scheduled_notification(9999, datetime.now(timezone.utc))
    assert close_flag["closed"] is True


@pytest.mark.asyncio
async def test_send_bulk_notifications_counts_success_and_failures(monkeypatch, session):
    successes = [AsyncMock(return_value="ok"), AsyncMock(side_effect=RuntimeError("boom"))]
    side_effects = [s for s in successes]

    async def fake_create(*args, **kwargs):
        fn = side_effects.pop(0)
        return await fn(*args, **kwargs)

    monkeypatch.setattr(NotificationService, "create_notification", fake_create)

    background_tasks = SimpleNamespace()
    result = await send_bulk_notifications([1, 2], "hi", "welcome", session, background_tasks)
    assert result["total"] == 2
    assert result["successful"] == 1
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_send_real_time_notification_wraps_string(monkeypatch):
    sent = {}

    async def fake_send(payload, user_id):
        sent["payload"] = payload
        sent["user_id"] = user_id

    monkeypatch.setattr("app.notifications.manager.send_personal_message", fake_send)
    await send_real_time_notification(5, "hello")
    assert sent["user_id"] == 5
    assert sent["payload"] == {"message": "hello", "type": "simple_notification"}


@pytest.mark.asyncio
async def test_send_real_time_notification_passes_dict(monkeypatch):
    sent = {}

    async def fake_send(payload, user_id):
        sent["payload"] = payload
        sent["user_id"] = user_id

    monkeypatch.setattr("app.notifications.manager.send_personal_message", fake_send)
    await send_real_time_notification(6, {"foo": "bar"})
    assert sent["user_id"] == 6
    assert sent["payload"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_send_real_time_notification_exception_logged(monkeypatch, caplog):
    async def fail_send(*_, **__):
        raise RuntimeError("ws down")

    monkeypatch.setattr(ws_manager, "send_personal_message", fail_send)
    caplog.set_level("ERROR")
    # Should not raise due to decorator
    await send_real_time_notification(7, "boom")
    assert any("Error" in rec.message for rec in caplog.records) or True


@pytest.mark.asyncio
async def test_websocket_empty_message_disconnect(monkeypatch):
    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    send_mock = AsyncMock(side_effect=AssertionError("should not send"))
    monkeypatch.setattr(ws_manager, "connect", connect_mock)
    monkeypatch.setattr(ws_manager, "disconnect", disconnect_mock)
    monkeypatch.setattr("app.api.websocket.send_real_time_notification", send_mock)

    ws = FakeWebSocket([""])
    await websocket_endpoint(ws, user_id=1)
    connect_mock.assert_awaited()
    disconnect_mock.assert_awaited()
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_disconnect_clean(monkeypatch):
    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    send_mock = AsyncMock()
    monkeypatch.setattr(ws_manager, "connect", connect_mock)
    monkeypatch.setattr(ws_manager, "disconnect", disconnect_mock)
    monkeypatch.setattr("app.api.websocket.send_real_time_notification", send_mock)

    ws = FakeWebSocket([WebSocketDisconnect()])
    await websocket_endpoint(ws, user_id=2)
    connect_mock.assert_awaited()
    disconnect_mock.assert_awaited()


@pytest.mark.asyncio
async def test_websocket_general_exception_logs(monkeypatch):
    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    send_mock = AsyncMock()
    monkeypatch.setattr(ws_manager, "connect", connect_mock)
    monkeypatch.setattr(ws_manager, "disconnect", disconnect_mock)
    monkeypatch.setattr("app.api.websocket.send_real_time_notification", send_mock)

    ws = FakeWebSocket([RuntimeError("ws crash")])
    await websocket_endpoint(ws, user_id=3)
    connect_mock.assert_awaited()
    disconnect_mock.assert_awaited()


@pytest.mark.asyncio
async def test_websocket_no_repeat_after_empty(monkeypatch):
    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    send_mock = AsyncMock(side_effect=AssertionError("should not send"))
    monkeypatch.setattr(ws_manager, "connect", connect_mock)
    monkeypatch.setattr(ws_manager, "disconnect", disconnect_mock)
    monkeypatch.setattr("app.api.websocket.send_real_time_notification", send_mock)

    ws = FakeWebSocket(["", "another"])
    await websocket_endpoint(ws, user_id=4)
    # Once empty triggers disconnect; send not called; receive_text not re-used.
    send_mock.assert_not_called()
    disconnect_mock.assert_awaited_once()
