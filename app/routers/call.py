"""
Call Router Module
This module provides endpoints for handling calls, including starting calls,
updating call status, retrieving active calls, and managing WebSocket connections
for real-time call communication.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
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
from typing import List
from datetime import datetime, timezone, timedelta

# Local imports
from .. import models, schemas, oauth2, notifications, database
from ..database import get_db
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

# =====================================================
# =============== Global Variables ====================
# =====================================================
router = APIRouter(prefix="/calls", tags=["Calls"])
manager = ConnectionManager()  # Manages WebSocket connections for calls

# Interval for updating encryption key (every 30 minutes)
KEY_UPDATE_INTERVAL = timedelta(minutes=30)

# =====================================================
# =================== Endpoints =======================
# =====================================================


@router.post("/", response_model=schemas.CallOut, status_code=status.HTTP_201_CREATED)
async def start_call(
    call: schemas.CallCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Start a new call.

    Parameters:
      - call: CallCreate schema with call information.
      - db: Database session.
      - current_user: The authenticated caller.

    Process:
      - Verify the receiver exists.
      - Check that the number of active calls does not exceed the limit.
      - Generate an encryption key and create a new call record.
      - Send a real-time notification to the receiver.

    Returns:
      The newly created call record.
    """
    receiver = db.query(models.User).filter(models.User.id == call.receiver_id).first()
    if not receiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found"
        )

    active_calls_count = (
        db.query(models.Call)
        .filter(
            (models.Call.caller_id == current_user.id)
            | (models.Call.receiver_id == current_user.id),
            models.Call.status != models.CallStatus.ENDED,
        )
        .count()
    )
    if active_calls_count >= 5:
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
    """
    Update the status of an existing call.

    Parameters:
      - call_id: ID of the call.
      - call_update: CallUpdate schema with new status.
      - db: Database session.
      - current_user: The authenticated user (caller or receiver).

    If the status is updated to ENDED, also update the end time and any active screen share session.

    Returns:
      The updated call record.
    """
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
    """
    Retrieve a list of active calls for the current user.

    Returns:
      A list of active calls.
    """
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


@router.websocket("/ws/{call_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    call_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    WebSocket endpoint for call communication.

    Handles real-time data exchange during the call, manages encryption key updates,
    and checks call quality.
    """
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

            await _handle_encryption_key_update(call, db, other_user_id)
            await _handle_call_quality(
                data, call_id, db, current_user.id, other_user_id, background_tasks
            )
            await _handle_call_data(data, other_user_id, notifications)

    except WebSocketDisconnect:
        await _handle_call_disconnect(call, db, other_user_id)
        clean_old_quality_buffers()
    except Exception as e:
        await websocket.close(code=1011, reason="Internal server error")


def update_call_quality(db: Session, call_id: int, quality_score: int):
    """
    Update the call quality score in the database.
    """
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if call:
        call.quality_score = quality_score
        db.commit()


# =====================================================
# ============== Helper Functions =====================
# =====================================================


async def _handle_encryption_key_update(call, db, other_user_id):
    """
    Check if the encryption key needs to be updated based on KEY_UPDATE_INTERVAL.
    If so, update the key and notify both participants.
    """
    if datetime.now(timezone.utc) - call.last_key_update > KEY_UPDATE_INTERVAL:
        new_key = update_encryption_key(call.encryption_key)
        call.encryption_key = new_key
        call.last_key_update = datetime.now(timezone.utc)
        db.commit()
        for user_id in [call.caller_id, call.receiver_id]:
            await notifications.send_real_time_notification(
                user_id, {"type": "new_encryption_key", "key": new_key}
            )


async def _handle_call_quality(
    data, call_id, db, current_user_id, other_user_id, background_tasks
):
    """
    Check the call quality using provided data. If the quality has changed,
    update it in the database. If video quality adjustment is needed,
    notify both participants.
    """
    call_quality = check_call_quality(data, call_id)
    call = db.query(models.Call).filter(models.Call.id == call_id).first()
    if call_quality != call.quality_score:
        background_tasks.add_task(update_call_quality, db, call.id, call_quality)

    if should_adjust_video_quality(call_id):
        recommended_quality = get_recommended_video_quality(call_id)
        for user_id in [current_user_id, other_user_id]:
            await notifications.send_real_time_notification(
                user_id,
                {"type": "adjust_video_quality", "quality": recommended_quality},
            )


async def _handle_call_data(data, other_user_id, notifications):
    """
    Forward call signaling data to the other participant if the data type is valid.
    """
    valid_types = [
        "offer",
        "answer",
        "ice_candidate",
        "screen_share_offer",
        "screen_share_answer",
        "screen_share_ice_candidate",
        "screen_share_data",
    ]
    if data.get("type") in valid_types:
        await notifications.send_real_time_notification(other_user_id, data)


async def _handle_call_disconnect(call, db, other_user_id):
    """
    Handle call disconnect:
      - Update call status to ENDED.
      - Update end times for the call and any active screen share session.
      - Notify the other participant.
    """
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


# =====================================================
# ========== Periodic Tasks (Startup Event) =========
# =====================================================


@router.on_event("startup")
@repeat_every(seconds=3600)  # Execute every hour
def clean_quality_buffers_periodically():
    """
    Periodically clean old call quality buffers.
    """
    clean_old_quality_buffers()
