import io

import pytest
from starlette.datastructures import Headers, UploadFile

from app import models, notifications
from app.services.messaging.message_service import MessageService
from fastapi import HTTPException


def _make_user(session, email: str, *, hide_read: bool = False) -> models.User:
    user = models.User(
        email=email,
        hashed_password="x",
        is_verified=True,
        hide_read_status=hide_read,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class DummyBackgroundTasks:
    def __init__(self) -> None:
        self.calls = []

    def add_task(self, func, *args, **kwargs):
        self.calls.append((func, args, kwargs))


@pytest.mark.asyncio
async def test_send_file_empty_and_too_large(monkeypatch, session, tmp_path):
    monkeypatch.setattr(MessageService, "UPLOAD_DIR", tmp_path / "uploads")
    service = MessageService(session)
    sender = _make_user(session, "sender@example.com")
    recipient = _make_user(session, "recipient@example.com")

    empty_file = UploadFile(
        file=io.BytesIO(b""),
        filename="empty.txt",
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(HTTPException) as exc:
        await service.send_file(
            file=empty_file, recipient_id=recipient.id, current_user=sender
        )
    assert exc.value.status_code == 400

    monkeypatch.setattr(service, "MAX_FILE_SIZE", 10)
    large_file = UploadFile(
        file=io.BytesIO(b"a" * 11),
        filename="large.bin",
        headers=Headers({"content-type": "application/octet-stream"}),
    )
    with pytest.raises(HTTPException) as exc_large:
        await service.send_file(
            file=large_file, recipient_id=recipient.id, current_user=sender
        )
    assert exc_large.value.status_code == 413


@pytest.mark.asyncio
async def test_send_file_infected_removes_artifact(monkeypatch, session, tmp_path):
    monkeypatch.setattr(MessageService, "UPLOAD_DIR", tmp_path / "uploads")
    service = MessageService(session)
    sender = _make_user(session, "bad_sender@example.com")
    recipient = _make_user(session, "bad_recipient@example.com")
    monkeypatch.setattr(service, "_scan_file_for_viruses", lambda path: False)

    infected_file = UploadFile(
        file=io.BytesIO(b"malware"),
        filename="malware.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as exc:
        await service.send_file(
            file=infected_file, recipient_id=recipient.id, current_user=sender
        )
    assert exc.value.status_code == 400
    assert not (service.UPLOAD_DIR / "malware.txt").exists()


def test_get_or_create_direct_conversation_single_instance(session):
    service = MessageService(session)
    user_a = _make_user(session, "a@example.com")
    user_b = _make_user(session, "b@example.com")

    conv_first = service._get_or_create_direct_conversation(user_a.id, user_b.id)
    conv_second = service._get_or_create_direct_conversation(user_b.id, user_a.id)

    assert (
        conv_first
        == conv_second
        == f"{min(user_a.id, user_b.id)}_{max(user_a.id, user_b.id)}"
    )
    conv_count = session.query(models.Conversation).filter_by(id=conv_first).count()
    assert conv_count == 1

    members = (
        session.query(models.ConversationMember)
        .filter_by(conversation_id=conv_first)
        .all()
    )
    assert len(members) == 2
    roles = {m.user_id: m.role for m in members}
    assert roles[user_a.id] == models.ConversationMemberRole.OWNER
    assert roles[user_b.id] == models.ConversationMemberRole.MEMBER


@pytest.mark.asyncio
async def test_mark_message_as_read_notifies_sender(session):
    service = MessageService(session)
    sender = _make_user(session, "notify_sender@example.com")
    receiver = _make_user(session, "notify_receiver@example.com")
    conversation_id = service._get_or_create_direct_conversation(sender.id, receiver.id)
    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        conversation_id=conversation_id,
        content="hello",
        encrypted_content=b"hello",
        is_read=False,
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    bg = DummyBackgroundTasks()
    result = await service.mark_message_as_read(
        message_id=message.id, current_user=receiver, background_tasks=bg
    )

    assert result.is_read is True
    assert len(bg.calls) == 1
    func, args, kwargs = bg.calls[0]
    assert func == notifications.send_real_time_notification
    assert args[0] == sender.id
    assert "has been read" in args[1]


@pytest.mark.asyncio
async def test_mark_message_as_read_respects_hide_read_status(session):
    service = MessageService(session)
    sender = _make_user(session, "silent_sender@example.com", hide_read=True)
    receiver = _make_user(session, "silent_receiver@example.com")
    conversation_id = service._get_or_create_direct_conversation(sender.id, receiver.id)
    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        conversation_id=conversation_id,
        content="hi",
        encrypted_content=b"hi",
        is_read=False,
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    bg = DummyBackgroundTasks()
    result = await service.mark_message_as_read(
        message_id=message.id, current_user=receiver, background_tasks=bg
    )

    assert result.is_read is True
    assert bg.calls == []


@pytest.mark.asyncio
async def test_mark_message_as_read_missing_message(session):
    service = MessageService(session)
    current = _make_user(session, "missing@example.com")
    bg = DummyBackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await service.mark_message_as_read(
            message_id=9999, current_user=current, background_tasks=bg
        )
    assert exc.value.status_code == 404
