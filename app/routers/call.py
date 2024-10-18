from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
    BackgroundTasks,
)
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, notifications, database
from ..database import get_db
from typing import List
from datetime import datetime, timezone, timedelta
from ..notifications import ConnectionManager
from ..utils import (
    generate_encryption_key,
    update_encryption_key,
    check_call_quality,
    should_adjust_video_quality,
    get_recommended_video_quality,
    clean_old_quality_buffers,
)
from fastapi_utils.tasks import repeat_every


router = APIRouter(prefix="/calls", tags=["Calls"])
manager = ConnectionManager()

KEY_UPDATE_INTERVAL = timedelta(minutes=30)


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

    # Проверка на количество активных вызовов пользователя
    active_calls_count = (
        db.query(models.Call)
        .filter(
            (models.Call.caller_id == current_user.id)
            | (models.Call.receiver_id == current_user.id),
            models.Call.status != models.CallStatus.ENDED,
        )
        .count()
    )
    if active_calls_count >= 5:  # Ограничение на 5 активных вызовов
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of active calls reached",
        )

    encryption_key = generate_encryption_key()
    new_call = models.Call(
        caller_id=current_user.id,
        receiver_id=call.receiver_id,
        call_type=call.call_type,
        status=models.CallStatus.PENDING,
        encryption_key=encryption_key,
        last_key_update=datetime.now(timezone.utc),
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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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

            # التحقق وتحديث مفتاح التشفير
            if datetime.now(timezone.utc) - call.last_key_update > KEY_UPDATE_INTERVAL:
                new_key = update_encryption_key(call.encryption_key)
                call.encryption_key = new_key
                call.last_key_update = datetime.now(timezone.utc)
                db.commit()
                await notifications.send_real_time_notification(
                    call.caller_id, {"type": "new_encryption_key", "key": new_key}
                )
                await notifications.send_real_time_notification(
                    call.receiver_id, {"type": "new_encryption_key", "key": new_key}
                )

            # التحقق من جودة المكالمة
            call_quality = check_call_quality(data, call_id)
            if call_quality != call.quality_score:
                background_tasks.add_task(
                    update_call_quality, db, call.id, call_quality
                )

            # التحقق مما إذا كان يجب ضبط جودة الفيديو
            if should_adjust_video_quality(call_id):
                recommended_quality = get_recommended_video_quality(call_id)
                await notifications.send_real_time_notification(
                    current_user.id,
                    {"type": "adjust_video_quality", "quality": recommended_quality},
                )
                await notifications.send_real_time_notification(
                    other_user_id,
                    {"type": "adjust_video_quality", "quality": recommended_quality},
                )

            # معالجة أنواع البيانات المختلفة
            if data["type"] in ["offer", "answer", "ice_candidate"]:
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_offer":
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_answer":
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_ice_candidate":
                await notifications.send_real_time_notification(other_user_id, data)
            elif data["type"] == "screen_share_data":
                await notifications.send_real_time_notification(other_user_id, data)

    except WebSocketDisconnect:
        # معالجة قطع الاتصال
        call.status = models.CallStatus.ENDED
        call.end_time = datetime.now(timezone.utc)

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

        await notifications.send_real_time_notification(
            other_user_id, {"type": "call_ended", "call_id": call.id}
        )

        # تنظيف بيانات جودة المكالمة القديمة
        clean_old_quality_buffers()


# يجب إضافة هذه الوظيفة لتشغيلها بشكل دوري (مثلاً كل ساعة) لتنظيف البيانات القديمة
@router.on_event("startup")
@repeat_every(seconds=3600)  # كل ساعة
def clean_quality_buffers_periodically():
    clean_old_quality_buffers()


def update_call_quality(db: Session, call_id: int, quality_score: int):
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if call:
        call.quality_score = quality_score
        db.commit()
