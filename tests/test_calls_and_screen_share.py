from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import models, oauth2
from app.main import app
from app.modules.messaging.models import CallStatus, ScreenShareStatus


@pytest.fixture
def caller_client(authorized_client, test_user):
    # override current user to be caller
    app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(
        **test_user
    )
    yield authorized_client
    app.dependency_overrides.pop(oauth2.get_current_user, None)


def test_call_start_update_and_end(session, caller_client, test_user, test_user2):
    # start call
    res = caller_client.post(
        "/calls/",
        json={"receiver_id": test_user2["id"], "call_type": "audio"},
    )
    assert res.status_code == 201
    call_id = res.json()["id"]

    call_record = session.query(models.Call).filter_by(id=call_id).first()
    assert call_record is not None
    assert call_record.status == CallStatus.PENDING

    # update status to ongoing then ended
    res_ongoing = caller_client.put(
        f"/calls/{call_id}", json={"status": "ongoing", "current_screen_share_id": None}
    )
    assert res_ongoing.status_code == 200
    res_end = caller_client.put(
        f"/calls/{call_id}", json={"status": "ended", "current_screen_share_id": None}
    )
    assert res_end.status_code == 200

    updated = session.query(models.Call).filter_by(id=call_id).first()
    assert updated.status == CallStatus.ENDED
    assert updated.end_time is not None


def test_screen_share_start_and_end(session, caller_client, test_user, test_user2):
    # ensure Call has attribute used by router even if not mapped
    if not hasattr(models.Call, "current_screen_share_id"):
        setattr(models.Call, "current_screen_share_id", None)
    # create call directly in DB
    call = models.Call(
        caller_id=test_user["id"],
        receiver_id=test_user2["id"],
        call_type="video",
        status=CallStatus.ONGOING,
        start_time=datetime.now(timezone.utc),
        encryption_key="tmp",
        quality_score=100,
        last_key_update=datetime.now(timezone.utc),
    )
    session.add(call)
    session.commit()
    session.refresh(call)

    start_res = caller_client.post("/screen-share/start", json={"call_id": call.id})
    assert start_res.status_code == 200
    share_id = start_res.json()["id"]

    session_share = (
        session.query(models.ScreenShareSession).filter_by(id=share_id).first()
    )
    assert session_share is not None
    assert session_share.status == ScreenShareStatus.ACTIVE
    assert call.current_screen_share_id == share_id

    end_res = caller_client.post("/screen-share/end", json={"session_id": share_id})
    assert end_res.status_code == 200

    from sqlalchemy.orm import sessionmaker

    check_session = sessionmaker(bind=session.get_bind())()
    updated_share = (
        check_session.query(models.ScreenShareSession).filter_by(id=share_id).first()
    )
    assert updated_share.status == ScreenShareStatus.ENDED
    assert updated_share.end_time is not None
    check_session.close()
