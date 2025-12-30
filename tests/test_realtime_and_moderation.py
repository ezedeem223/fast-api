import pytest

import app.firebase_config as firebase_config
import app.link_preview as link_preview
from app import models, schemas
from app.modules.notifications.realtime import ConnectionManager
from app.services.moderation.banned_word_service import BannedWordService

# -----------------------
# WebSocket realtime
# -----------------------


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.closed:
            raise RuntimeError("socket closed")
        self.sent.append(data)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_connection_manager_send_and_disconnect():
    manager = ConnectionManager()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await manager.connect(ws1, user_id=1)
    await manager.connect(ws2, user_id=1)

    await manager.send_personal_message({"hello": "world"}, user_id=1)
    assert ws1.sent == [{"hello": "world"}]
    assert ws2.sent == [{"hello": "world"}]

    # simulate a broken socket
    ws1.closed = True
    await manager.send_personal_message({"next": True}, user_id=1)
    assert ws2.sent[-1] == {"next": True}
    # broken socket should be removed from connections
    assert ws1 not in manager.active_connections.get(1, [])

    await manager.disconnect(ws1, 1)
    assert ws1 not in manager.active_connections.get(1, [])


# -----------------------
# Firebase config stubs
# -----------------------


def test_initialize_firebase_failure(monkeypatch):
    monkeypatch.setattr(
        firebase_config.credentials,
        "Certificate",
        lambda cfg: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    assert firebase_config.initialize_firebase() is False


def test_send_multicast_notification_handles_errors(monkeypatch):
    monkeypatch.setattr(
        firebase_config.messaging, "MulticastMessage", lambda **kwargs: kwargs
    )
    monkeypatch.setattr(firebase_config.messaging, "send_multicast", lambda msg: "ok")
    assert firebase_config.send_multicast_notification(["t1"], "t", "b") == "ok"
    monkeypatch.setattr(
        firebase_config.messaging,
        "send_multicast",
        lambda msg: (_ for _ in ()).throw(RuntimeError("fail")),
    )
    assert firebase_config.send_multicast_notification(["t1"], "t", "b") is None


def test_send_topic_notification(monkeypatch):
    monkeypatch.setattr(firebase_config.messaging, "Message", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        firebase_config.messaging, "Notification", lambda **kwargs: kwargs
    )
    monkeypatch.setattr(firebase_config.messaging, "send", lambda msg: "id123")
    assert firebase_config.send_topic_notification("news", "hi", "there") == "id123"


# -----------------------
# Link preview
# -----------------------


def test_extract_link_preview_success(monkeypatch):
    html = """
    <html><head><title>Title</title>
    <meta name="description" content="desc">
    <meta property="og:image" content="img.png">
    </head><body></body></html>
    """

    class DummyResponse:
        def __init__(self, content):
            self.content = content

    monkeypatch.setattr(link_preview.validators, "url", lambda u: True)
    monkeypatch.setattr(
        link_preview.requests, "get", lambda u, timeout=5: DummyResponse(html.encode())
    )
    preview = link_preview.extract_link_preview("http://example.com")
    assert preview["title"] == "Title"
    assert preview["description"] == "desc"
    assert preview["image"] == "img.png"


def test_extract_link_preview_invalid_url(monkeypatch):
    monkeypatch.setattr(link_preview.validators, "url", lambda u: False)
    assert link_preview.extract_link_preview("not-a-url") is None


# -----------------------
# Banned words service
# -----------------------


def _make_admin(session):
    user = models.User(
        email="admin@example.com", hashed_password="hashed", is_verified=True
    )
    session.add(user)
    session.commit()
    return user


def test_banned_word_crud(session, monkeypatch):
    monkeypatch.setattr(
        "app.services.moderation.banned_word_service.update_ban_statistics",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.moderation.banned_word_service.log_admin_action",
        lambda *args, **kwargs: None,
    )
    service = BannedWordService(session)
    admin = _make_admin(session)

    word = service.add_word(
        payload=schemas.BannedWordCreate(word="spam"), current_user=admin
    )
    assert word.id

    with pytest.raises(Exception):
        service.add_word(
            payload=schemas.BannedWordCreate(word="spam"), current_user=admin
        )

    listed = service.list_words(
        skip=0, limit=10, search="sp", sort_by="word", sort_order="asc"
    )
    assert listed["total"] == 1
    assert listed["words"][0]["word"] == "spam"

    updated = service.update_word(
        word_id=word.id,
        update_payload=schemas.BannedWordUpdate(word="eggs"),
        current_user=admin,
    )
    assert updated.word == "eggs"

    bulk = service.add_bulk(
        payloads=[schemas.BannedWordCreate(word="foo")], current_user=admin
    )
    assert bulk["added_words"] == 1

    removed = service.remove_word(word_id=word.id, current_user=admin)
    assert removed["message"].startswith("Banned word removed")
