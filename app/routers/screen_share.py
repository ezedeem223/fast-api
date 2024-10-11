from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from datetime import datetime
from ..notifications import ConnectionManager

router = APIRouter(prefix="/screen-share", tags=["Screen Share"])
manager = ConnectionManager()


@router.post("/start", response_model=schemas.ScreenShareSessionOut)
async def start_screen_share(
    screen_share: schemas.ScreenShareStart,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    call = db.query(models.Call).filter(models.Call.id == screen_share.call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.caller_id != current_user.id and call.receiver_id != current_user.id:
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

    # Notify other participants
    other_user_id = (
        call.receiver_id if current_user.id == call.caller_id else call.caller_id
    )
    await manager.send_personal_message(
        {"type": "screen_share_started", "session_id": new_session.id}, other_user_id
    )

    return new_session


@router.post("/end", response_model=schemas.ScreenShareSessionOut)
async def end_screen_share(
    screen_share: schemas.ScreenShareEnd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    session = (
        db.query(models.ScreenShareSession)
        .filter(models.ScreenShareSession.id == screen_share.session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Screen share session not found")

    if session.sharer_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to end this screen share session"
        )

    session.end_time = datetime.now()
    session.status = models.ScreenShareStatus.ENDED
    db.commit()
    db.refresh(session)

    # Update the call to remove the current screen share session
    call = db.query(models.Call).filter(models.Call.id == session.call_id).first()
    if call and call.current_screen_share_id == session.id:
        call.current_screen_share_id = None
        db.commit()

    # Notify other participants
    other_user_id = (
        call.receiver_id if current_user.id == call.caller_id else call.caller_id
    )
    await manager.send_personal_message(
        {"type": "screen_share_ended", "session_id": session.id}, other_user_id
    )

    return session


@router.put("/update", response_model=schemas.ScreenShareSessionOut)
async def update_screen_share(
    session_id: int,
    update_data: schemas.ScreenShareUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    session = (
        db.query(models.ScreenShareSession)
        .filter(models.ScreenShareSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Screen share session not found")

    if session.sharer_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this screen share session"
        )

    session.status = update_data.status
    session.error_message = update_data.error_message
    if update_data.status == models.ScreenShareStatus.ENDED:
        session.end_time = datetime.now()

    db.commit()
    db.refresh(session)

    # Notify other participants about the update
    call = db.query(models.Call).filter(models.Call.id == session.call_id).first()
    if call:
        other_user_id = (
            call.receiver_id if current_user.id == call.caller_id else call.caller_id
        )
        await manager.send_personal_message(
            {
                "type": "screen_share_updated",
                "session_id": session.id,
                "status": update_data.status,
            },
            other_user_id,
        )

    return session


@router.websocket("/ws/{call_id}")
async def screen_share_websocket(
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
            data = await websocket.receive_text()
            # Here you would process the screen share data and send it to other participants
            # For example:
            other_user_id = (
                call.receiver_id
                if current_user.id == call.caller_id
                else call.caller_id
            )
            await manager.send_personal_message(
                {"type": "screen_share_data", "data": data}, other_user_id
            )
    except WebSocketDisconnect:
        # Handle WebSocket disconnection
        active_share = (
            db.query(models.ScreenShareSession)
            .filter(
                models.ScreenShareSession.call_id == call_id,
                models.ScreenShareSession.status == models.ScreenShareStatus.ACTIVE,
                models.ScreenShareSession.sharer_id == current_user.id,
            )
            .first()
        )
        if active_share:
            active_share.status = models.ScreenShareStatus.ENDED
            active_share.end_time = datetime.now()
            db.commit()
