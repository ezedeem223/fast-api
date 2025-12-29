from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from app import models, schemas
from app.analytics import update_conversation_statistics
from app.routers import session as session_router
from app.services.messaging.message_service import MessageService
from tests.conftest import TestingSessionLocal


def _user(session, email="msg10@example.com"):
    u = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_text_message_creates_stats(monkeypatch, session):
    service = MessageService(session)
    sender = _user(session, "s10@example.com")
    recv = _user(session, "r10@example.com")
    tasks = BackgroundTasks()

    # Silence side effects
    async def _noop_translate(*args, **kwargs):
        return args[0]

    monkeypatch.setattr("app.services.messaging.message_service.get_translated_content", _noop_translate)
    monkeypatch.setattr("app.services.messaging.message_service.create_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.manager.send_personal_message", lambda *a, **k: None)
    monkeypatch.setattr("app.notifications.send_real_time_notification", lambda *a, **k: None)

    msg = await service.create_message(
        payload=schemas.MessageCreate(content="hello", receiver_id=recv.id),
        current_user=sender,
        background_tasks=tasks,
    )
    stats = (
        session.query(models.ConversationStatistics)
        .filter_by(conversation_id=msg.conversation_id)
        .first()
    )
    assert stats is not None
    assert stats.total_messages == 1


@pytest.mark.asyncio
async def test_send_file_oversized(monkeypatch, session):
    service = MessageService(session)
    sender = _user(session, "f10@example.com")
    recv = _user(session, "f210@example.com")
    big_bytes = b"x" * (service.MAX_FILE_SIZE + 1)
    upload = UploadFile(file=BytesIO(big_bytes), filename="big.bin")
    with pytest.raises(HTTPException) as exc:
        await service.send_file(file=upload, recipient_id=recv.id, current_user=sender)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_unknown_sticker_rejected(session):
    service = MessageService(session)
    sender = _user(session, "stk10@example.com")
    recv = _user(session, "stk210@example.com")
    service._get_valid_sticker = lambda *_: None  # force lookup miss
    with pytest.raises(HTTPException) as exc:
        await service.create_message(
            payload=schemas.MessageCreate(content=None, receiver_id=recv.id, sticker_id=9999),
            current_user=sender,
            background_tasks=BackgroundTasks(),
        )
    assert exc.value.status_code == 404


def _stub_signal_protocol(monkeypatch):
    class StubDH:
        def public_key(self):
            return self

        def private_bytes_raw(self):
            return b"ratchet"

        def exchange(self, other):
            return b"shared"

    class StubSignal:
        def __init__(self):
            self.dh_pair = StubDH()
            self.root_key = b"root"
            self.chain_key = b"chain"
            self.next_header_key = b"next"

        def initial_key_exchange(self, other_public_key):
            return None

    monkeypatch.setattr(session_router.crypto, "SignalProtocol", StubSignal)


def test_create_encrypted_session_stores_keys(monkeypatch, authorized_client, test_user2):
    _stub_signal_protocol(monkeypatch)
    resp = authorized_client.post("/sessions", json={"other_user_id": test_user2["id"]})
    assert resp.status_code == 201
    sess_id = resp.json()["id"]
    with TestingSessionLocal() as db:
        stored = db.get(models.EncryptedSession, sess_id)
        assert stored is not None
        assert stored.root_key is not None


def test_update_session_persists_chain_key(monkeypatch, authorized_client, test_user2):
    _stub_signal_protocol(monkeypatch)
    created = authorized_client.post("/sessions", json={"other_user_id": test_user2["id"]}).json()
    update = authorized_client.put(
        f"/sessions/{created['id']}",
        json={
            "root_key": "r",
            "chain_key": "new_chain",
            "next_header_key": "n",
            "ratchet_key": "rk",
        },
    )
    assert update.status_code == 200
    with TestingSessionLocal() as db:
        sess = db.get(models.EncryptedSession, created["id"])
        assert sess.chain_key == b"new_chain"


def test_update_session_missing_field(monkeypatch, authorized_client, test_user2):
    _stub_signal_protocol(monkeypatch)
    created = authorized_client.post("/sessions", json={"other_user_id": test_user2["id"]}).json()
    bad = authorized_client.put(
        f"/sessions/{created['id']}",
        json={
            "root_key": "r",
            "next_header_key": "n",
            "ratchet_key": "rk",
        },
    )
    assert bad.status_code == 422


def test_conversation_stats_response_and_files(session):
    sender = _user(session, "stats10@example.com")
    recv = _user(session, "stats210@example.com")
    conv_id = f"{min(sender.id, recv.id)}_{max(sender.id, recv.id)}"
    msg1 = models.Message(
        sender_id=sender.id,
        receiver_id=recv.id,
        conversation_id=conv_id,
        content="hello 😀",
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    msg1.has_emoji = True
    session.add(msg1)
    session.commit()
    session.add(
        models.MessageAttachment(
            message_id=msg1.id, file_url="file1", file_type="file"
        )
    )
    session.commit()

    session.refresh(msg1)
    update_conversation_statistics(session, conv_id, msg1)

    msg2 = models.Message(
        sender_id=recv.id,
        receiver_id=sender.id,
        conversation_id=conv_id,
        content="reply",
        timestamp=datetime.now(timezone.utc),
    )
    msg2.has_emoji = False
    session.add(msg2)
    session.commit()
    session.add(
        models.MessageAttachment(
            message_id=msg2.id, file_url="file2", file_type="file"
        )
    )
    session.add(
        models.MessageAttachment(
            message_id=msg2.id, file_url="file3", file_type="file"
        )
    )
    session.commit()

    session.refresh(msg2)
    update_conversation_statistics(session, conv_id, msg2)

    stats = (
        session.query(models.ConversationStatistics)
        .filter_by(conversation_id=conv_id)
        .first()
    )
    assert stats.total_messages == 2
    assert stats.total_files == 3
    assert stats.total_emojis >= 1
    assert stats.average_response_time > 0
