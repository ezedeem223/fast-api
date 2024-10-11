from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, notifications
from ..database import get_db
from typing import List
from datetime import datetime, timezone
from ..notifications import ConnectionManager

router = APIRouter(prefix="/calls", tags=["Calls"])
manager = ConnectionManager()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CallOut)
async def start_call(
    call: schemas.CallCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    receiver = db.query(models.User).filter(models.User.id == call.receiver_id).first()
    if not receiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found"
        )

    new_call = models.Call(
        caller_id=current_user.id,
        receiver_id=call.receiver_id,
        call_type=call.call_type,
        status=models.CallStatus.PENDING,
    )
    db.add(new_call)
    db.commit()
    db.refresh(new_call)

    # Send notification to receiver
    await notifications.send_real_time_notification(
        receiver.id, f"Incoming {call.call_type} call from {current_user.username}"
    )

    return new_call


@router.put("/{call_id}", response_model=schemas.CallOut)
async def update_call_status(
    call_id: int,
    call_update: schemas.CallUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )

    if current_user.id not in [call.caller_id, call.receiver_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this call",
        )

    call.status = call_update.status
    if call_update.status == models.CallStatus.ENDED:
        call.end_time = datetime.now(timezone.utc)
        # End any active screen share session
        active_share = (
            db.query(models.ScreenShareSession)
            .filter(
                models.ScreenShareSession.call_id == call.id,
                models.ScreenShareSession.status == models.ScreenShareStatus.ACTIVE,
            )
            .first()
        )
        if active_share:
            active_share.status = models.ScreenShareStatus.ENDED
            active_share.end_time = datetime.now(timezone.utc)

    db.commit()
    db.refresh(call)
    return call


@router.get("/active", response_model=List[schemas.CallOut])
async def get_active_calls(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    active_calls = (
        db.query(models.Call)
        .filter(
            (models.Call.caller_id == current_user.id)
            | (models.Call.receiver_id == current_user.id),
            models.Call.status != models.CallStatus.ENDED,
        )
        .all()
    )
    return active_calls


@router.post("/{call_id}/screen-share", response_model=schemas.ScreenShareSessionOut)
async def start_screen_share(
    call_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if current_user.id not in [call.caller_id, call.receiver_id]:
        raise HTTPException(
            status_code=403, detail="Not authorized to share screen in this call"
        )

    active_share = (
        db.query(models.ScreenShareSession)
        .filter(
            models.ScreenShareSession.call_id == call.id,
            models.ScreenShareSession.status == models.ScreenShareStatus.ACTIVE,
        )
        .first()
    )

    if active_share:
        raise HTTPException(
            status_code=400,
            detail="There's already an active screen share in this call",
        )

    new_session = models.ScreenShareSession(call_id=call.id, sharer_id=current_user.id)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Update the call with the current screen share session
    call.current_screen_share_id = new_session.id
    db.commit()

    # Notify other participant
    other_user_id = (
        call.receiver_id if current_user.id == call.caller_id else call.caller_id
    )
    await notifications.send_real_time_notification(
        other_user_id, {"type": "screen_share_started", "session_id": new_session.id}
    )

    return new_session


@router.post(
    "/{call_id}/screen-share/{session_id}/end",
    response_model=schemas.ScreenShareSessionOut,
)
async def end_screen_share(
    call_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    session = (
        db.query(models.ScreenShareSession)
        .filter(
            models.ScreenShareSession.id == session_id,
            models.ScreenShareSession.call_id == call_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Screen share session not found")

    if session.sharer_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to end this screen share session"
        )

    session.end_time = datetime.now(timezone.utc)
    session.status = models.ScreenShareStatus.ENDED
    call.current_screen_share_id = None
    db.commit()
    db.refresh(session)

    # Notify other participant
    other_user_id = (
        call.receiver_id if current_user.id == call.caller_id else call.caller_id
    )
    await notifications.send_real_time_notification(
        other_user_id, {"type": "screen_share_ended", "session_id": session.id}
    )

    return session


@router.websocket("/ws/{call_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    call_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    await websocket.accept()
    try:
        call = db.query(models.Call).filter(models.Call.id == call_id).first()
        if not call or current_user.id not in [call.caller_id, call.receiver_id]:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        while True:
            data = await websocket.receive_json()
            other_user_id = (
                call.receiver_id
                if current_user.id == call.caller_id
                else call.caller_id
            )

            if data["type"] in ["offer", "answer", "ice_candidate"]:
                # Handle WebRTC signaling (offer, answer, ICE candidates)
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_offer":
                # Handle screen share offer
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_answer":
                # Handle screen share answer
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_ice_candidate":
                # Handle ICE candidates for screen sharing
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_data":
                # Handle screen share data
                await notifications.send_real_time_notification(other_user_id, data)

    except WebSocketDisconnect:
        # Handle disconnection
        call.status = models.CallStatus.ENDED
        call.end_time = datetime.now(timezone.utc)

        # End any active screen share session
        active_share = (
            db.query(models.ScreenShareSession)
            .filter(
                models.ScreenShareSession.call_id == call.id,
                models.ScreenShareSession.status == models.ScreenShareStatus.ACTIVE,
            )
            .first()
        )
        if active_share:
            active_share.status = models.ScreenShareStatus.ENDED
            active_share.end_time = datetime.now(timezone.utc)

        db.commit()

        # Notify the other participant about the disconnection
        other_user_id = (
            call.receiver_id if current_user.id == call.caller_id else call.caller_id
        )
        await notifications.send_real_time_notification(
            other_user_id, {"type": "call_ended", "call_id": call.id}
        )
