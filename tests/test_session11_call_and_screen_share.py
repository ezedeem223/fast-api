from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import models, oauth2
from app.main import app
from app.modules.messaging.models import CallStatus, ScreenShareStatus
from app.routers import call as call_router


@pytest.fixture
def caller_client(authorized_client, test_user):
    app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(
        **test_user
    )
    yield authorized_client
    app.dependency_overrides.pop(oauth2.get_current_user, None)


def _make_call(session, caller_id, receiver_id):
    call = models.Call(
        caller_id=caller_id,
        receiver_id=receiver_id,
        call_type="video",
        status=CallStatus.ONGOING,
        start_time=datetime.now(timezone.utc),
        encryption_key="k",
        quality_score=100,
        last_key_update=datetime.now(timezone.utc),
    )
    session.add(call)
    session.commit()
    session.refresh(call)
    return call


def test_start_call_sets_pending_and_notifies(
    monkeypatch, caller_client, session, test_user2
):
    sent = {}

    async def fake_notify(user_id, payload):
        sent["user_id"] = user_id
        sent["payload"] = payload

    monkeypatch.setattr(
        "app.services.messaging.call_service.notifications.send_real_time_notification",
        fake_notify,
    )

    resp = caller_client.post(
        "/calls/",
        json={"receiver_id": test_user2["id"], "call_type": "audio"},
    )
    assert resp.status_code == 201
    call_id = resp.json()["id"]
    db_call = session.get(models.Call, call_id)
    assert db_call.status == CallStatus.PENDING
    assert db_call.encryption_key
    assert sent["user_id"] == test_user2["id"]
    assert "Incoming" in sent["payload"]


def test_update_call_ended_marks_end_and_screen_share(
    caller_client, session, test_user, test_user2
):
    resp = caller_client.post(
        "/calls/",
        json={"receiver_id": test_user2["id"], "call_type": "video"},
    )
    call_id = resp.json()["id"]
    share = models.ScreenShareSession(
        call_id=call_id, sharer_id=test_user["id"], status=ScreenShareStatus.ACTIVE
    )
    session.add(share)
    session.commit()
    share_id = share.id

    end_resp = caller_client.put(
        f"/calls/{call_id}", json={"status": "ended", "current_screen_share_id": None}
    )
    assert end_resp.status_code == 200
    updated_call = session.get(models.Call, call_id)
    updated_share = session.get(models.ScreenShareSession, share_id)
    assert updated_call.status == CallStatus.ENDED
    assert updated_call.end_time is not None
    assert updated_share.status == ScreenShareStatus.ENDED
    assert updated_share.end_time is not None


def test_update_call_forbidden_for_non_participant(
    caller_client, client, session, test_user2
):
    start_resp = caller_client.post(
        "/calls/",
        json={"receiver_id": test_user2["id"], "call_type": "video"},
    )
    call_id = start_resp.json()["id"]

    stranger = models.User(
        email="stranger@example.com", hashed_password="x", is_verified=True
    )
    session.add(stranger)
    session.commit()
    session.refresh(stranger)

    app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(
        id=stranger.id, email=stranger.email
    )
    try:
        res = client.put(
            f"/calls/{call_id}",
            json={"status": "ended", "current_screen_share_id": None},
        )
    finally:
        app.dependency_overrides.pop(oauth2.get_current_user, None)

    assert res.status_code == 403


def test_start_screen_share_sets_active_and_notifies(
    monkeypatch, caller_client, session, test_user2
):
    messages = {}

    async def fake_personal(msg, user_id):
        messages["payload"] = msg
        messages["user_id"] = user_id

    monkeypatch.setattr(
        "app.routers.screen_share.manager.send_personal_message",
        fake_personal,
    )

    call_resp = caller_client.post(
        "/calls/", json={"receiver_id": test_user2["id"], "call_type": "video"}
    )
    call_id = call_resp.json()["id"]

    start_resp = caller_client.post("/screen-share/start", json={"call_id": call_id})
    assert start_resp.status_code == 200
    share_id = start_resp.json()["id"]
    share = session.get(models.ScreenShareSession, share_id)
    assert share.status == ScreenShareStatus.ACTIVE
    assert messages["user_id"] == test_user2["id"]
    assert messages["payload"]["type"] == "screen_share_started"


def test_start_screen_share_rejects_duplicate_active(
    caller_client, session, test_user, test_user2
):
    call_resp = caller_client.post(
        "/calls/", json={"receiver_id": test_user2["id"], "call_type": "video"}
    )
    call_id = call_resp.json()["id"]
    existing = models.ScreenShareSession(
        call_id=call_id,
        sharer_id=test_user["id"],
    )
    session.add(existing)
    session.commit()

    res = caller_client.post("/screen-share/start", json={"call_id": call_id})
    assert res.status_code == 400


def test_update_screen_share_status_ended(
    monkeypatch, caller_client, session, test_user, test_user2
):
    notified = {}

    async def fake_personal(msg, user_id):
        notified["msg"] = msg
        notified["user_id"] = user_id

    monkeypatch.setattr(
        "app.routers.screen_share.manager.send_personal_message",
        fake_personal,
    )

    call_resp = caller_client.post(
        "/calls/", json={"receiver_id": test_user2["id"], "call_type": "video"}
    )
    call_id = call_resp.json()["id"]
    share = models.ScreenShareSession(
        call_id=call_id, sharer_id=test_user["id"], status=ScreenShareStatus.ACTIVE
    )
    session.add(share)
    session.commit()
    session.refresh(share)

    upd = caller_client.put(
        f"/screen-share/update?session_id={share.id}",
        json={"status": "ended", "error_message": "done"},
    )
    assert upd.status_code == 200
    refreshed = session.get(models.ScreenShareSession, share.id)
    assert refreshed.status == ScreenShareStatus.ENDED
    assert refreshed.end_time is not None
    assert refreshed.error_message == "done"
    assert notified["user_id"] == test_user2["id"]
    assert notified["msg"]["type"] == "screen_share_updated"


def test_end_screen_share_requires_owner(
    caller_client, client, session, test_user, test_user2
):
    call = _make_call(session, caller_id=test_user["id"], receiver_id=test_user2["id"])
    share = models.ScreenShareSession(
        call_id=call.id, sharer_id=test_user2["id"], status=ScreenShareStatus.ACTIVE
    )
    session.add(share)
    session.commit()

    res = caller_client.post("/screen-share/end", json={"session_id": share.id})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_handle_call_data_forwards_valid_types(monkeypatch):
    sent = {}

    class StubNotif:
        async def send_real_time_notification(self, user_id, payload):
            sent.setdefault("calls", []).append((user_id, payload))

    await call_router._handle_call_data({"type": "offer", "sdp": "x"}, 42, StubNotif())
    await call_router._handle_call_data({"type": "ignored"}, 99, StubNotif())
    assert any(p[1]["type"] == "offer" for p in sent["calls"])
    assert all(p[0] == 42 for p in sent["calls"])


@pytest.mark.asyncio
async def test_handle_call_disconnect_sets_status_and_notifies(monkeypatch, session):
    caller = models.User(email="c11@example.com", hashed_password="x", is_verified=True)
    receiver = models.User(
        email="r11@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([caller, receiver])
    session.commit()
    session.refresh(caller)
    session.refresh(receiver)
    call = _make_call(session, caller_id=caller.id, receiver_id=receiver.id)
    share = models.ScreenShareSession(
        call_id=call.id, sharer_id=caller.id, status=ScreenShareStatus.ACTIVE
    )
    session.add(share)
    session.commit()

    notified = {}

    async def fake_notify(user_id, payload):
        notified.setdefault("messages", []).append((user_id, payload))

    monkeypatch.setattr(
        "app.routers.call.notifications.send_real_time_notification",
        fake_notify,
    )

    await call_router._handle_call_disconnect(call, session, receiver.id)
    session.refresh(call)
    updated_share = session.get(models.ScreenShareSession, share.id)
    assert call.status == CallStatus.ENDED
    assert call.end_time is not None
    assert updated_share.status == ScreenShareStatus.ENDED
    assert notified["messages"][0][1]["type"] == "call_ended"
