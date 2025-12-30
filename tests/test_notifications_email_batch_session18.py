from types import SimpleNamespace

import pytest
from fastapi_mail import MessageSchema

from app.core.config import settings
from app.modules.notifications import batching, email
from app.modules.notifications.batching import NotificationBatcher


@pytest.mark.asyncio
async def test_send_email_notification_skips_in_test_env(monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")

    # Should return early without raising, even if recipients are missing.
    await email.send_email_notification(to="user@example.com", subject="hi", body="body")


@pytest.mark.asyncio
async def test_send_email_notification_requires_recipient(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")

    with pytest.raises(ValueError):
        await email.send_email_notification(message=None, to=None)


@pytest.mark.asyncio
async def test_send_email_notification_skips_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")
    monkeypatch.setattr(settings, "mail_username", "")
    monkeypatch.setattr(settings, "mail_password", "")

    called = {"sent": False}

    async def fake_send_message(message):
        called["sent"] = True

    monkeypatch.setattr(email, "fm", SimpleNamespace(send_message=fake_send_message))
    message = MessageSchema(
        subject="Test", recipients=["a@example.com"], body="body", subtype="plain"
    )

    await email.send_email_notification(message)
    assert called["sent"] is False


@pytest.mark.asyncio
async def test_send_email_notification_sends_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setenv("DISABLE_EXTERNAL_NOTIFICATIONS", "0")
    monkeypatch.setattr(settings, "mail_username", "user")
    monkeypatch.setattr(settings, "mail_password", "pass")

    sent = {}

    async def fake_send_message(message):
        sent["message"] = message

    monkeypatch.setattr(email, "fm", SimpleNamespace(send_message=fake_send_message))
    message = MessageSchema(
        subject="Hello", recipients=["dest@example.com"], body="ok", subtype="plain"
    )

    await email.send_email_notification(message)
    assert sent["message"].recipients == ["dest@example.com"]
    assert sent["message"].subject == "Hello"


@pytest.mark.asyncio
async def test_schedule_email_notification_by_id_fetches_and_sends(monkeypatch):
    notification = SimpleNamespace(
        notification_type="new_comment", user_id=7, content="payload"
    )
    user = SimpleNamespace(email="user@example.com")

    class DummySession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    dummy_session = DummySession()

    def fake_get_db():
        yield dummy_session

    def fake_get_model_by_id(session, model, object_id):
        if model is email.models.Notification:
            return notification
        if model is email.models.User:
            return user
        return None

    sent = {}

    async def fake_send_email(message):
        sent["message"] = message

    async def immediate_sleep(_):
        return None

    tasks = []

    def capture_task(coro):
        tasks.append(coro)
        return SimpleNamespace(done=lambda: True)

    monkeypatch.setattr(email, "get_db", fake_get_db)
    monkeypatch.setattr(email, "get_model_by_id", fake_get_model_by_id)
    monkeypatch.setattr(email, "send_email_notification", fake_send_email)
    monkeypatch.setattr(email.asyncio, "sleep", immediate_sleep)
    monkeypatch.setattr(email.asyncio, "create_task", capture_task)

    email.schedule_email_notification_by_id(42, delay=0)
    assert tasks, "Expected the coroutine to be scheduled"
    await tasks[0]

    assert dummy_session.closed is True
    assert sent["message"].recipients == [user.email]
    assert sent["message"].subject == "Notification: New Comment"
    assert sent["message"].body == "payload"


@pytest.mark.asyncio
async def test_send_mention_notification_builds_message(monkeypatch):
    captured = {}

    async def fake_send(message):
        captured["message"] = message

    monkeypatch.setattr(email, "send_email_notification", fake_send)
    await email.send_mention_notification("mention@example.com", "alice", 123)

    msg = captured["message"]
    assert msg.subject == "You've been mentioned by alice"
    assert "View Post" in msg.body
    assert "123" in msg.body


@pytest.mark.asyncio
async def test_send_login_notification_builds_message(monkeypatch):
    captured = {}

    async def fake_send(message):
        captured["message"] = message

    monkeypatch.setattr(email, "send_email_notification", fake_send)
    await email.send_login_notification("user@example.com", "1.1.1.1", "AgentX")

    msg = captured["message"]
    assert "New Login" in msg.subject
    assert "1.1.1.1" in msg.body
    assert "AgentX" in msg.body


@pytest.mark.asyncio
async def test_batcher_add_flushes_on_size(monkeypatch):
    batcher = NotificationBatcher(max_batch_size=2, max_wait_time=100)
    processed = []

    async def fake_process(notifs):
        processed.append(list(notifs))

    batcher._process_batch = fake_process  # type: ignore[assignment]

    await batcher.add({"channel": "email", "recipient": "a", "title": "t1", "content": "c1"})
    assert processed == []
    await batcher.add({"channel": "email", "recipient": "b", "title": "t2", "content": "c2"})
    assert len(processed) == 1
    assert len(processed[0]) == 2


@pytest.mark.asyncio
async def test_batcher_add_flushes_on_time(monkeypatch):
    batcher = NotificationBatcher(max_batch_size=10, max_wait_time=0)
    processed = []

    async def fake_process(notifs):
        processed.append(list(notifs))

    batcher._process_batch = fake_process  # type: ignore[assignment]

    await batcher.add({"channel": "email", "recipient": "a", "title": "t", "content": "c"})
    assert len(processed) == 1
    assert processed[0][0]["recipient"] == "a"


@pytest.mark.asyncio
async def test_batcher_digest_flushes_on_size(monkeypatch):
    batcher = NotificationBatcher(digest_max_size=2, digest_window_seconds=100)
    sent = []

    async def fake_send(recipient, bucket):
        sent.append((recipient, list(bucket)))

    batcher._send_digest_email = fake_send  # type: ignore[assignment]

    await batcher.add_digest({"recipient": "user@example.com", "title": "t1", "content": "c1"})
    assert sent == []
    await batcher.add_digest({"recipient": "user@example.com", "title": "t2", "content": "c2"})
    assert len(sent) == 1
    assert len(sent[0][1]) == 2


@pytest.mark.asyncio
async def test_flush_digests_sends_all(monkeypatch):
    batcher = NotificationBatcher()
    batcher._digest_batches = {
        "a@example.com": [{"title": "t"}],
        "b@example.com": [{"title": "u"}],
    }

    sent = []

    async def fake_send(recipient, bucket):
        sent.append((recipient, bucket))

    batcher._send_digest_email = fake_send  # type: ignore[assignment]

    await batcher.flush_digests()
    assert ("a@example.com", [{"title": "t"}]) in sent
    assert ("b@example.com", [{"title": "u"}]) in sent


@pytest.mark.asyncio
async def test_process_batch_routes_channels(monkeypatch):
    batcher = NotificationBatcher()
    routes = {"email": None, "push": None, "in_app": None}

    async def fake_email(notifs):
        routes["email"] = notifs

    async def fake_push(notifs):
        routes["push"] = notifs

    async def fake_in_app(notifs):
        routes["in_app"] = notifs

    batcher._send_batch_emails = fake_email  # type: ignore[assignment]
    batcher._send_batch_push = fake_push  # type: ignore[assignment]
    batcher._send_batch_in_app = fake_in_app  # type: ignore[assignment]

    await batcher._process_batch(
        [
            {"channel": "email", "recipient": "a", "title": "t1", "content": "c1"},
            {"channel": "push", "recipient": "a", "title": "t2", "content": "c2"},
            {"channel": "other", "recipient": "a", "title": "t3", "content": "c3"},
        ]
    )

    assert len(routes["email"]) == 1
    assert len(routes["push"]) == 1
    assert len(routes["in_app"]) == 1


@pytest.mark.asyncio
async def test_send_batch_emails_groups_by_recipient(monkeypatch):
    batcher = NotificationBatcher()
    sent = []

    async def fake_send_email(message):
        sent.append(message)

    monkeypatch.setattr(batching, "send_email_notification", fake_send_email)

    await batcher._send_batch_emails(
        [
            {
                "channel": "email",
                "recipient": "a@example.com",
                "title": "t1",
                "content": "c1",
            },
            {
                "channel": "email",
                "recipient": "a@example.com",
                "title": "t2",
                "content": "c2",
            },
            {
                "channel": "email",
                "recipient": "b@example.com",
                "title": "t3",
                "content": "c3",
            },
        ]
    )

    assert len(sent) == 2
    assert sent[0].recipients == ["a@example.com"]
    assert "t1" in sent[0].body and "t2" in sent[0].body
    assert sent[1].recipients == ["b@example.com"]
    assert "t3" in sent[1].body


@pytest.mark.asyncio
async def test_send_digest_email_formats_content(monkeypatch):
    batcher = NotificationBatcher()
    sent = []

    async def fake_send_email(message):
        sent.append(message)

    monkeypatch.setattr(batching, "send_email_notification", fake_send_email)

    notifications = [
        {"title": "Update1", "content": "First", "created_at": "2024-01-01"},
        {"title": "Update2", "content": "Second", "created_at": "2024-01-02"},
    ]

    await batcher._send_digest_email("user@example.com", notifications)

    assert len(sent) == 1
    assert sent[0].recipients == ["user@example.com"]
    assert "Update1" in sent[0].body and "Update2" in sent[0].body
