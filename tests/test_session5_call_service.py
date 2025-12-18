import pytest
from datetime import datetime, timezone

from fastapi import HTTPException

from app import models, schemas
from app.services.messaging.call_service import CallService
from app.modules.utils.security import hash as hash_password


def _user(session, email="call@example.com"):
    user = models.User(email=email, hashed_password=hash_password("x"), is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class _StubNotifications:
    def __init__(self):
        self.sent = []

    async def send_real_time_notification(self, user_id, message):
        self.sent.append((user_id, message))


@pytest.mark.asyncio
async def test_start_call_success_and_limits(session):
    service = CallService(session)
    caller = _user(session, "caller@example.com")
    receiver = _user(session, "receiver@example.com")
    stub = _StubNotifications()

    call = await service.start_call(
        payload=schemas.CallCreate(receiver_id=receiver.id, call_type=models.CallType.VIDEO),
        current_user=caller,
        notification_backend=stub,
    )
    assert call.status == models.CallStatus.PENDING
    assert call.encryption_key
    assert stub.sent[-1][0] == receiver.id

    # pre-fill active calls to hit the limit
    for _ in range(5):
        session.add(
            models.Call(
                caller_id=caller.id,
                receiver_id=receiver.id,
                call_type=models.CallType.AUDIO,
                status=models.CallStatus.ONGOING,
                encryption_key="k",
                last_key_update=datetime.now(timezone.utc),
            )
        )
    session.commit()

    with pytest.raises(HTTPException) as exc:
        await service.start_call(
            payload=schemas.CallCreate(receiver_id=receiver.id, call_type=models.CallType.AUDIO),
            current_user=caller,
            notification_backend=stub,
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await service.start_call(
            payload=schemas.CallCreate(receiver_id=999999, call_type=models.CallType.AUDIO),
            current_user=caller,
            notification_backend=stub,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_call_status_permissions_and_end_share(session):
    service = CallService(session)
    caller = _user(session, "caller2@example.com")
    receiver = _user(session, "receiver2@example.com")
    outsider = _user(session, "outsider@example.com")

    call = models.Call(
        caller_id=caller.id,
        receiver_id=receiver.id,
        call_type=models.CallType.VIDEO,
        status=models.CallStatus.PENDING,
        encryption_key="k",
        last_key_update=datetime.now(timezone.utc),
    )
    session.add(call)
    session.commit()

    screen_share = models.ScreenShareSession(
        call_id=call.id,
        sharer_id=caller.id,
        status=models.ScreenShareStatus.ACTIVE,
        start_time=datetime.now(timezone.utc),
    )
    session.add(screen_share)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        await service.update_call_status(
            call_id=call.id,
            payload=schemas.CallUpdate(status=models.CallStatus.ONGOING),
            current_user=outsider,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await service.update_call_status(
            call_id=999999,
            payload=schemas.CallUpdate(status=models.CallStatus.ENDED),
            current_user=caller,
        )
    assert exc.value.status_code == 404

    ended = await service.update_call_status(
        call_id=call.id,
        payload=schemas.CallUpdate(status=models.CallStatus.ENDED),
        current_user=caller,
    )
    assert ended.status == models.CallStatus.ENDED
    refreshed_share = session.get(models.ScreenShareSession, screen_share.id)
    assert refreshed_share.status == models.ScreenShareStatus.ENDED
    assert refreshed_share.end_time is not None


def test_active_calls_and_quality_update(session):
    service = CallService(session)
    user = _user(session, "active@example.com")
    other = _user(session, "other@example.com")

    active_call = models.Call(
        caller_id=user.id,
        receiver_id=other.id,
        call_type=models.CallType.AUDIO,
        status=models.CallStatus.ONGOING,
        encryption_key="k",
        last_key_update=datetime.now(timezone.utc),
    )
    ended_call = models.Call(
        caller_id=user.id,
        receiver_id=other.id,
        call_type=models.CallType.VIDEO,
        status=models.CallStatus.ENDED,
        encryption_key="k2",
        last_key_update=datetime.now(timezone.utc),
    )
    session.add_all([active_call, ended_call])
    session.commit()

    active = service.get_active_calls(current_user=user)
    assert all(c.status != models.CallStatus.ENDED for c in active)

    service.update_call_quality(call_id=active_call.id, quality_score=42)
    updated_call = session.get(models.Call, active_call.id)
    assert updated_call.quality_score == 42
