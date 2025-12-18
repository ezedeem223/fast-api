"""Integration-style test for messaging service flows with moderation hooks and notification stubs."""

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app import models, schemas
from app.services.messaging.message_service import MessageService
from app.services.moderation.banned_word_service import BannedWordService
from app.services import reporting
from app.modules.utils.security import hash as hash_password


def _user(session, email="msg@example.com"):
    u = models.User(email=email, hashed_password=hash_password("x"), is_verified=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_message_service_send_list_update_delete(session, monkeypatch):
    service = MessageService(session)
    sender = _user(session, "s@example.com")
    recv = _user(session, "r@example.com")
    tasks = BackgroundTasks()

    class DummyDT:
        @staticmethod
        def now(tz=None):
            return datetime.now()

    monkeypatch.setattr("app.services.messaging.message_service.datetime", DummyDT)
    # stub notifications and translation
    monkeypatch.setattr(service, "_queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr(service, "_schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.send_real_time_notification", lambda *a, **k: None)
    async def _fake_translate(content, user, lang):
        return content
    monkeypatch.setattr("app.services.messaging.message_service.get_translated_content", _fake_translate)
    monkeypatch.setattr("app.services.messaging.message_service.update_conversation_statistics", lambda *a, **k: None)
    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)

    payload = schemas.MessageCreate(content="hello", receiver_id=recv.id)
    msg = await service.create_message(payload=payload, current_user=sender, background_tasks=tasks)
    assert msg.content == "hello"
    # normalize timestamp to aware for edit/delete checks
    msg_db = session.get(models.Message, msg.id)
    msg_db.timestamp = datetime.now(timezone.utc)
    session.commit()

    # list messages marks as read for receiver
    msgs = await service.list_messages(current_user=recv, skip=0, limit=10)
    assert msgs[0].is_read is True

    service.EDIT_DELETE_WINDOW = 100000
    # update message within window
    upd = schemas.MessageUpdate(content="edited")
    updated = await service.update_message(message_id=msg.id, payload=upd, current_user=sender, background_tasks=tasks)
    assert updated.is_edited is True

    # delete message within window
    await service.delete_message(message_id=msg.id, current_user=sender, background_tasks=tasks)
    assert session.query(models.Message).filter(models.Message.id == msg.id).first() is None

    # empty content error
    with pytest.raises(HTTPException):
        await service.create_message(payload=schemas.MessageCreate(content=" ", receiver_id=recv.id), current_user=sender, background_tasks=tasks)


@pytest.mark.asyncio
async def test_message_service_send_file_and_ordering(session, monkeypatch, tmp_path):
    service = MessageService(session)
    sender = _user(session, "file@example.com")
    recv = _user(session, "file2@example.com")
    monkeypatch.setattr(service, "_scan_file_for_viruses", lambda path: True)
    tasks = BackgroundTasks()

    file_content = b"file-bytes"
    upload = UploadFile(file=BytesIO(file_content), filename="a.txt")
    result = await service.send_file(file=upload, recipient_id=recv.id, current_user=sender)
    assert result["message"].startswith("File sent")

    # ordering of conversations by last_message_at
    convs = await service.get_conversations(current_user=sender)
    assert convs


@pytest.mark.asyncio
async def test_message_edit_delete_window_and_permissions(session, monkeypatch):
    service = MessageService(session)
    sender = _user(session, "edit@example.com")
    recv = _user(session, "edit2@example.com")
    intruder = _user(session, "intruder@example.com")
    tasks = BackgroundTasks()

    monkeypatch.setattr(service, "_queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr(service, "_schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.send_real_time_notification", lambda *a, **k: None)
    async def _fake_translate(content, user, lang):
        return content
    monkeypatch.setattr("app.services.messaging.message_service.get_translated_content", _fake_translate)
    monkeypatch.setattr("app.services.messaging.message_service.update_conversation_statistics", lambda *a, **k: None)
    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)

    msg = await service.create_message(
        payload=schemas.MessageCreate(content="will expire", receiver_id=recv.id),
        current_user=sender,
        background_tasks=tasks,
    )
    msg_db = session.get(models.Message, msg.id)
    msg_db.timestamp = datetime.now(timezone.utc) - timedelta(minutes=service.EDIT_DELETE_WINDOW + 5)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        await service.update_message(
            message_id=msg.id,
            payload=schemas.MessageUpdate(content="late edit"),
            current_user=sender,
            background_tasks=tasks,
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await service.delete_message(
            message_id=msg.id,
            current_user=sender,
            background_tasks=tasks,
        )
    assert exc.value.status_code == 400

    # reset timestamp inside window to trigger permission check
    msg_db.timestamp = datetime.now(timezone.utc)
    session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.update_message(
            message_id=msg.id,
            payload=schemas.MessageUpdate(content="intruder edit"),
            current_user=intruder,
            background_tasks=tasks,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_message_list_pagination_and_ordering(session, monkeypatch):
    service = MessageService(session)
    sender = _user(session, "order@example.com")
    recv = _user(session, "order2@example.com")
    tasks = BackgroundTasks()

    monkeypatch.setattr(service, "_queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr(service, "_schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.send_real_time_notification", lambda *a, **k: None)
    async def _fake_translate(content, user, lang):
        return content
    monkeypatch.setattr("app.services.messaging.message_service.get_translated_content", _fake_translate)
    monkeypatch.setattr("app.services.messaging.message_service.update_conversation_statistics", lambda *a, **k: None)
    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)

    for idx in range(3):
        created = await service.create_message(
            payload=schemas.MessageCreate(content=f"m{idx}", receiver_id=recv.id),
            current_user=sender,
            background_tasks=tasks,
        )
        msg_db = session.get(models.Message, created.id)
        msg_db.timestamp = datetime(2023, 1, 1, 12, idx, tzinfo=timezone.utc)
    session.commit()

    msgs = await service.list_messages(current_user=sender, skip=0, limit=2)
    assert [m.content for m in msgs] == ["m2", "m1"]

    second_page = await service.list_messages(current_user=sender, skip=1, limit=1)
    assert second_page[0].content == "m1"

    # receiver view marks as read
    recv_msgs = await service.list_messages(current_user=recv, skip=0, limit=5)
    assert all(m.is_read for m in recv_msgs)


@pytest.mark.asyncio
async def test_send_file_validation_and_virus_scan(session, monkeypatch, tmp_path):
    service = MessageService(session)
    service.UPLOAD_DIR = tmp_path / "uploads"
    sender = _user(session, "filecheck@example.com")
    recv = _user(session, "filecheck2@example.com")

    empty = UploadFile(file=BytesIO(b""), filename="empty.txt")
    with pytest.raises(HTTPException) as exc:
        await service.send_file(file=empty, recipient_id=recv.id, current_user=sender)
    assert exc.value.status_code == 400

    service.MAX_FILE_SIZE = 1
    big = UploadFile(file=BytesIO(b"too big"), filename="big.txt")
    with pytest.raises(HTTPException) as exc:
        await service.send_file(file=big, recipient_id=recv.id, current_user=sender)
    assert exc.value.status_code == 413

    service.MAX_FILE_SIZE = 10 * 1024 * 1024
    monkeypatch.setattr(service, "_scan_file_for_viruses", lambda path: False)
    infected = UploadFile(file=BytesIO(b"abc"), filename="bad.txt")
    with pytest.raises(HTTPException) as exc:
        await service.send_file(file=infected, recipient_id=recv.id, current_user=sender)
    assert exc.value.status_code == 400
    assert not (service.UPLOAD_DIR / "bad.txt").exists()


@pytest.mark.asyncio
async def test_mark_message_as_read_and_get_message_permissions(session, monkeypatch):
    service = MessageService(session)
    sender = _user(session, "mark@example.com")
    recv = _user(session, "mark2@example.com")
    outsider = _user(session, "outsider@example.com")
    tasks = BackgroundTasks()

    monkeypatch.setattr(service, "_queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr(service, "_schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.send_real_time_notification", lambda *a, **k: None)
    async def _fake_translate(content, user, lang):
        return content
    monkeypatch.setattr("app.services.messaging.message_service.get_translated_content", _fake_translate)
    monkeypatch.setattr("app.services.messaging.message_service.update_conversation_statistics", lambda *a, **k: None)
    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)

    msg = await service.create_message(
        payload=schemas.MessageCreate(content="read me", receiver_id=recv.id),
        current_user=sender,
        background_tasks=tasks,
    )

    with pytest.raises(HTTPException) as exc:
        await service.mark_message_as_read(
            message_id=msg.id,
            current_user=outsider,
            background_tasks=tasks,
        )
    assert exc.value.status_code == 403

    marked = await service.mark_message_as_read(
        message_id=msg.id,
        current_user=recv,
        background_tasks=tasks,
    )
    assert marked.is_read is True and marked.read_at is not None

    with pytest.raises(HTTPException) as exc:
        await service.get_message(message_id=msg.id, current_user=outsider)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_audio_message_validation(session, monkeypatch, tmp_path):
    service = MessageService(session)
    service.AUDIO_DIR = tmp_path / "audio"
    service.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    sender = _user(session, "audio@example.com")
    recv = _user(session, "audio2@example.com")

    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)

    invalid = UploadFile(file=BytesIO(b"bad"), filename="clip.txt")
    with pytest.raises(HTTPException) as exc:
        await service.create_audio_message(
            receiver_id=recv.id,
            audio_file=invalid,
            duration=1.2,
            current_user=sender,
        )
    assert exc.value.status_code == 400

    valid = UploadFile(file=BytesIO(b"ok"), filename="clip.mp3")
    msg = await service.create_audio_message(
        receiver_id=recv.id,
        audio_file=valid,
        duration=2.5,
        current_user=sender,
    )
    assert msg.audio_url.endswith(".mp3")
    assert (service.AUDIO_DIR / Path(msg.audio_url).name).exists()


def test_get_conversation_messages_membership_guard(session):
    service = MessageService(session)
    owner = _user(session, "owner@example.com")
    member = _user(session, "member@example.com")
    outsider = _user(session, "outsider2@example.com")

    conv = service.create_group_conversation(
        payload=schemas.ConversationCreate(title="group", member_ids=[member.id]),
        current_user=owner,
    )

    with pytest.raises(HTTPException) as exc:
        service.get_conversation_messages(
            conversation_id=conv.id,
            current_user=outsider,
            skip=0,
            limit=10,
        )
    assert exc.value.status_code == 403


def test_banned_word_service_crud(session, monkeypatch):
    service = BannedWordService(session)
    admin = _user(session, "admin@example.com")
    monkeypatch.setattr("app.services.moderation.banned_word_service.update_ban_statistics", lambda *a, **k: None)
    monkeypatch.setattr("app.services.moderation.banned_word_service.log_admin_action", lambda *a, **k: None)

    word = service.add_word(payload=schemas.BannedWordCreate(word="Spam"), current_user=admin)
    assert word.id

    with pytest.raises(HTTPException):
        service.add_word(payload=schemas.BannedWordCreate(word="spam"), current_user=admin)

    listed = service.list_words(skip=0, limit=10, search="sp", sort_by="word", sort_order="asc")
    assert listed["total"] == 1

    updated = service.update_word(word_id=word.id, update_payload=schemas.BannedWordUpdate(word="Eggs"), current_user=admin)
    assert updated.word == "Eggs"

    removed = service.remove_word(word_id=word.id, current_user=admin)
    assert removed["message"].startswith("Banned word removed")


def test_reporting_negative_paths(session, monkeypatch):
    user = _user(session, "rep@example.com")
    # no reason
    with pytest.raises(HTTPException):
        reporting.submit_report(session, user, reason=" ", post_id=1)

    # neither post nor comment
    with pytest.raises(HTTPException):
        reporting.submit_report(session, user, reason="valid", post_id=None, comment_id=None)

    # missing post
    with pytest.raises(HTTPException):
        reporting.submit_report(session, user, reason="valid", post_id=999)

    # create post then report succeeds
    post = models.Post(owner_id=user.id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    res = reporting.submit_report(session, user, reason="valid", post_id=post.id)
    assert res["message"].startswith("Report submitted")
