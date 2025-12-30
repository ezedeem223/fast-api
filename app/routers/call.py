"""Call router for audio/video call setup, updates, and screen-share integration.

Handles call lifecycle (start/update/active list), WebSocket exchange, encryption key
rotation, and quality tracking. Relies on CallService for persistence and uses
ConnectionManager to fan out realtime events between participants.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi_utils.tasks import repeat_every
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.messaging.models import (
    Call,
    CallStatus,
    ScreenShareSession,
    ScreenShareStatus,
)
from app.modules.users.models import User
from app.modules.utils.analytics import (
    check_call_quality,
    clean_old_quality_buffers,
    get_recommended_video_quality,
    should_adjust_video_quality,
)
from app.modules.utils.security import update_encryption_key
from app.services.messaging import CallService
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    status,
)

# Local imports
from .. import notifications, oauth2, schemas
from ..notifications import ConnectionManager

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


def get_call_service(db: Session = Depends(get_db)) -> CallService:
    """Endpoint: get_call_service."""
    return CallService(db)


@router.post("/", response_model=schemas.CallOut, status_code=status.HTTP_201_CREATED)
async def start_call(
    call: schemas.CallCreate,
    current_user: User = Depends(oauth2.get_current_user),
    service: CallService = Depends(get_call_service),
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
    return await service.start_call(payload=call, current_user=current_user)


@router.put("/{call_id}", response_model=schemas.CallOut)
async def update_call_status(
    call_id: int,
    call_update: schemas.CallUpdate,
    current_user: User = Depends(oauth2.get_current_user),
    service: CallService = Depends(get_call_service),
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
    return await service.update_call_status(
        call_id=call_id,
        payload=call_update,
        current_user=current_user,
    )


@router.get("/active", response_model=List[schemas.CallOut])
async def get_active_calls(
    current_user: User = Depends(oauth2.get_current_user),
    service: CallService = Depends(get_call_service),
):
    """
    Retrieve a list of active calls for the current user.

    Returns:
      A list of active calls.
    """
    return service.get_active_calls(current_user=current_user)


@router.websocket("/ws/{call_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    call_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    WebSocket endpoint for call communication.

    Handles real-time data exchange during the call, manages encryption key updates,
    and checks call quality.
    """
    await websocket.accept()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
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
    except Exception:
        await websocket.close(code=1011, reason="Internal server error")


def update_call_quality(db: Session, call_id: int, quality_score: int):
    """Endpoint: update_call_quality."""
    CallService(db).update_call_quality(call_id=call_id, quality_score=quality_score)


# =====================================================
# ============== Helper Functions =====================
# =====================================================


async def _handle_encryption_key_update(call, db, other_user_id):
    """Endpoint: _handle_encryption_key_update."""
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
    """Endpoint: _handle_call_quality."""
    call_quality = check_call_quality(data, call_id)
    call = db.query(Call).filter(Call.id == call_id).first()
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
    """Endpoint: _handle_call_data."""
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
    """Endpoint: _handle_call_disconnect."""
    call.status = CallStatus.ENDED
    call.end_time = datetime.now(timezone.utc)

    active_share = (
        db.query(ScreenShareSession)
        .filter(
            ScreenShareSession.call_id == call.id,
            ScreenShareSession.status == ScreenShareStatus.ACTIVE,
        )
        .first()
    )
    if active_share:
        active_share.status = ScreenShareStatus.ENDED
        active_share.end_time = datetime.now(timezone.utc)

    db.commit()
    await notifications.send_real_time_notification(
        other_user_id, {"type": "call_ended", "call_id": call.id}
    )


# =====================================================
# ========== Periodic Tasks (Startup Event) =========
# =====================================================


@repeat_every(seconds=3600)  # Execute every hour
def clean_quality_buffers_periodically():
    """Endpoint: clean_quality_buffers_periodically."""
    clean_old_quality_buffers()


router.add_event_handler("startup", clean_quality_buffers_periodically)
