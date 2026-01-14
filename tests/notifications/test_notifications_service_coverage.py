"""Coverage-focused tests for notification services and handlers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import models
from app.modules.notifications import models as notification_models
from app.modules.notifications import service as notification_service
from app.modules.notifications.common import notification_cache


@pytest.mark.asyncio
async def test_notification_service_metadata_and_schedule(session, monkeypatch):
    user = models.User(email="notify@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    service = notification_service.NotificationService(session)
    assert service._normalize_metadata({"ok": True}) == {"ok": True}
    assert service._normalize_metadata({1, 2}) == {}

    with pytest.raises(ValueError):
        service._normalize_metadata({"blob": "x" * 3000})

    scheduled_for = datetime.now(timezone.utc) + timedelta(hours=1)
    scheduled = {}

    monkeypatch.setattr(service, "_schedule_delivery", lambda n: scheduled.setdefault("id", n.id))
    monkeypatch.setattr(notification_service, "detect_language", lambda text: "en")
    monkeypatch.setattr(notification_service, "translate_text", lambda *args, **kwargs: None)

    notif = await service.create_notification(
        user_id=user.id,
        content="hello",
        notification_type="system_update",
        scheduled_for=scheduled_for,
    )
    assert notif.scheduled_for is not None
    stored = notif.scheduled_for
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored == scheduled_for
    assert scheduled["id"] == notif.id


@pytest.mark.asyncio
async def test_delivery_manager_no_channels(session):
    user = models.User(email="prefs@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    notification_cache.clear()
    prefs = notification_models.NotificationPreferences(
        user_id=user.id,
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=False,
    )
    session.add(prefs)
    session.commit()

    notif = notification_models.Notification(
        user_id=user.id,
        content="no channels",
        notification_type="system_update",
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    manager = notification_service.NotificationDeliveryManager(session)
    result = await manager.deliver_notification(notif)
    assert result is False


@pytest.mark.asyncio
async def test_delivery_manager_email_send(session, monkeypatch):
    user = models.User(email="email@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    notif = notification_models.Notification(
        user_id=user.id,
        content="email content",
        notification_type="system_update",
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    sent = {}

    async def fake_send_email(message):
        sent["recipients"] = message.recipients

    monkeypatch.setattr(notification_service, "send_email_notification", fake_send_email)

    manager = notification_service.NotificationDeliveryManager(session)
    await manager._send_email_notification(notif, "email content")
    assert sent["recipients"] == [user.email]


@pytest.mark.asyncio
async def test_notification_retry_handler_states(session):
    notif = notification_models.Notification(
        user_id=1,
        content="retry",
        notification_type="system_update",
        status=notification_models.NotificationStatus.FAILED,
        retry_count=0,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)

    calls = []
    background = SimpleNamespace(add_task=lambda *args, **kwargs: calls.append(args))
    handler = notification_service.NotificationRetryHandler(session, background)

    await handler.handle_failed_notification(notif.id)
    session.refresh(notif)
    assert notif.status == "retrying"
    assert notif.retry_count == 1
    assert calls

    exhausted = notification_models.Notification(
        user_id=1,
        content="exhausted",
        notification_type="system_update",
        status=notification_models.NotificationStatus.FAILED,
        retry_count=handler.max_retries,
    )
    session.add(exhausted)
    session.commit()
    session.refresh(exhausted)

    await handler.handle_failed_notification(exhausted.id)
    session.refresh(exhausted)
    assert exhausted.status == notification_models.NotificationStatus.PERMANENTLY_FAILED


@pytest.mark.asyncio
async def test_comment_and_message_handlers(session, monkeypatch):
    owner = models.User(email="owner@example.com", hashed_password="x", is_verified=True)
    commenter = models.User(
        email="commenter@example.com", hashed_password="x", is_verified=True
    )
    owner.username = "owner"
    commenter.username = "commenter"
    session.add_all([owner, commenter])
    session.commit()
    session.refresh(owner)
    session.refresh(commenter)

    post = models.Post(owner_id=owner.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    parent = models.Comment(owner_id=owner.id, post_id=post.id, content="p")
    session.add(parent)
    session.commit()
    session.refresh(parent)

    comment = models.Comment(
        owner_id=commenter.id, post_id=post.id, content="c", parent_id=parent.id
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)

    calls = []

    async def fake_create(self, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(notification_service.NotificationService, "create_notification", fake_create)

    handler = notification_service.CommentNotificationHandler(
        session, SimpleNamespace(add_task=lambda *args, **kwargs: None)
    )
    await handler.handle_new_comment(comment, post)
    assert len(calls) == 2

    msg_calls = []

    async def fake_message_create(self, **kwargs):
        msg_calls.append(kwargs)

    monkeypatch.setattr(notification_service.NotificationService, "create_notification", fake_message_create)

    message_handler = notification_service.MessageNotificationHandler(
        session, SimpleNamespace(add_task=lambda *args, **kwargs: None)
    )
    message = SimpleNamespace(
        receiver_id=owner.id,
        sender_id=commenter.id,
        sender=SimpleNamespace(username="commenter"),
        message_type=SimpleNamespace(value="text"),
        conversation_id=1,
    )
    await message_handler.handle_new_message(message)
    assert msg_calls
