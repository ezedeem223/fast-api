"""Test module for test message service session20."""
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app import models, notifications
from app.modules.messaging import MessageType
from app.modules.messaging.schemas import MessageSearch, MessageUpdate, SortOrder
from app.services.messaging.message_service import MessageService
from fastapi import HTTPException


def _user(session, email: str) -> models.User:
    """Helper for  user."""
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class DummyBackgroundTasks:
    """Test class for DummyBackgroundTasks."""
    def __init__(self):
        self.calls = []

    def add_task(self, func, *args, **kwargs):
        self.calls.append((func, args, kwargs))


@pytest.mark.asyncio
async def test_save_message_attachments_writes_files(monkeypatch, session, tmp_path):
    """Test case for test save message attachments writes files."""
    monkeypatch.setattr(MessageService, "UPLOAD_DIR", tmp_path / "msgs")
    service = MessageService(session)
    new_message = models.Message(
        sender_id=1,
        receiver_id=2,
        encrypted_content=b"",
        conversation_id="1_2",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(timezone.utc),
    )
    files = [
        UploadFile(
            file=io.BytesIO(b"hello"),
            filename="a.txt",
            headers=Headers({"content-type": "text/plain"}),
        ),
        UploadFile(
            file=io.BytesIO(b"world"),
            filename="b.txt",
            headers=Headers({"content-type": "text/plain"}),
        ),
    ]

    await service._save_message_attachments(files, new_message)

    assert len(new_message.attachments) == 2
    for attachment in new_message.attachments:
        assert (tmp_path / "msgs" / Path(attachment.file_url).name).exists()


@pytest.mark.asyncio
async def test_save_message_attachments_enforces_size(monkeypatch, session, tmp_path):
    """Test case for test save message attachments enforces size."""
    monkeypatch.setattr(MessageService, "UPLOAD_DIR", tmp_path / "msgs")
    service = MessageService(session)
    service.MAX_FILE_SIZE = 1
    new_message = models.Message(
        sender_id=1,
        receiver_id=2,
        encrypted_content=b"",
        conversation_id="1_2",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(timezone.utc),
    )
    big_file = UploadFile(
        file=io.BytesIO(b"ab"),
        filename="big.bin",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    with pytest.raises(HTTPException) as exc:
        await service._save_message_attachments([big_file], new_message)
    assert exc.value.status_code == 413
    assert exc.value.detail == "File is too large"


@pytest.mark.asyncio
async def test_save_message_attachments_io_error(monkeypatch, session, tmp_path):
    """Test case for test save message attachments io error."""
    monkeypatch.setattr(MessageService, "UPLOAD_DIR", tmp_path / "msgs")
    service = MessageService(session)
    new_message = models.Message(
        sender_id=1,
        receiver_id=2,
        encrypted_content=b"",
        conversation_id="1_2",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(timezone.utc),
    )
    failing_file = UploadFile(
        file=io.BytesIO(b"data"),
        filename="fail.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    def boom_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom_open)
    with pytest.raises(OSError):
        await service._save_message_attachments([failing_file], new_message)


@pytest.mark.asyncio
async def test_search_messages_filters_and_sort(session):
    """Test case for test search messages filters and sort."""
    # Arrange: create a conversation with mixed message types/timestamps.
    service = MessageService(session)
    user = _user(session, "searcher@example.com")
    other = _user(session, "other@example.com")
    conversation_id = service._get_or_create_direct_conversation(user.id, other.id)

    old_ts = datetime.now(timezone.utc) - timedelta(days=2)
    new_ts = datetime.now(timezone.utc) - timedelta(hours=1)

    msg_old = models.Message(
        sender_id=user.id,
        receiver_id=other.id,
        conversation_id=conversation_id,
        content="older file",
        encrypted_content=b"older",
        timestamp=old_ts,
        message_type=MessageType.FILE,
    )
    msg_new = models.Message(
        sender_id=other.id,
        receiver_id=user.id,
        conversation_id=conversation_id,
        content="new text",
        encrypted_content=b"new",
        timestamp=new_ts,
        message_type=MessageType.TEXT,
    )
    session.add_all([msg_old, msg_new])
    session.commit()

    # Act: search for recent text messages in ascending order.
    params = MessageSearch(
        start_date=datetime.now(timezone.utc) - timedelta(days=1),
        message_type=MessageType.TEXT,
        sort_order=SortOrder.ASC,
    )
    result = await service.search_messages(
        params=params, current_user=user, skip=0, limit=10
    )

    # Assert: only the expected message is returned and ordered.
    assert result.total == 1
    assert result.messages[0].content == "new text"
    result_ts = result.messages[0].timestamp
    if result_ts.tzinfo is None:
        result_ts = result_ts.replace(tzinfo=timezone.utc)
    assert result_ts == new_ts


def test_message_search_invalid_sort_rejected():
    """Test case for test message search invalid sort rejected."""
    with pytest.raises(Exception):
        MessageSearch(sort_order="invalid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_message_success_and_notifications(session):
    """Test case for test update message success and notifications."""
    service = MessageService(session)
    sender = _user(session, "edit_sender@example.com")
    receiver = _user(session, "edit_receiver@example.com")
    conv_id = service._get_or_create_direct_conversation(sender.id, receiver.id)
    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        conversation_id=conv_id,
        content="orig",
        encrypted_content=b"orig",
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    bg = DummyBackgroundTasks()
    updated = await service.update_message(
        message_id=message.id,
        payload=MessageUpdate(content="edited"),
        current_user=sender,
        background_tasks=bg,
    )

    assert updated.content == "edited"
    assert updated.is_edited is True
    assert any(
        call[0] == notifications.send_real_time_notification for call in bg.calls
    )


@pytest.mark.asyncio
async def test_update_message_expired_window(session):
    """Test case for test update message expired window."""
    service = MessageService(session)
    sender = _user(session, "expired_sender@example.com")
    receiver = _user(session, "expired_receiver@example.com")
    conv_id = service._get_or_create_direct_conversation(sender.id, receiver.id)
    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        conversation_id=conv_id,
        content="too old",
        encrypted_content=b"old",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    bg = DummyBackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await service.update_message(
            message_id=message.id,
            payload=MessageUpdate(content="edit"),
            current_user=sender,
            background_tasks=bg,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Edit window has expired"


@pytest.mark.asyncio
async def test_update_message_non_sender_forbidden(session):
    """Test case for test update message non sender forbidden."""
    service = MessageService(session)
    sender = _user(session, "owner@example.com")
    other = _user(session, "intruder@example.com")
    receiver = _user(session, "receiver@example.com")
    conv_id = service._get_or_create_direct_conversation(sender.id, receiver.id)
    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        conversation_id=conv_id,
        content="secret",
        encrypted_content=b"secret",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(message)
    session.commit()
    session.refresh(message)

    bg = DummyBackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await service.update_message(
            message_id=message.id,
            payload=MessageUpdate(content="hack"),
            current_user=other,
            background_tasks=bg,
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to edit this message"
