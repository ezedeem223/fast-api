"""Service layer for call management: setup, status transitions, and quality safeguards."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import notifications, schemas
from app.modules.messaging.models import (
    Call,
    CallStatus,
    ScreenShareSession,
    ScreenShareStatus,
)
from app.modules.users.models import User
from app.modules.utils.security import generate_encryption_key


class CallService:
    """Encapsulates call CRUD logic shared between HTTP and WebSocket handlers."""

    def __init__(self, db: Session):
        self.db = db

    async def start_call(
        self,
        *,
        payload: schemas.CallCreate,
        current_user: User,
        notification_backend=notifications,
    ) -> Call:
        receiver = self.db.query(User).filter(User.id == payload.receiver_id).first()
        if not receiver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found"
            )

        active_calls_count = (
            self.db.query(Call)
            .filter(
                (Call.caller_id == current_user.id)
                | (Call.receiver_id == current_user.id),
                Call.status != CallStatus.ENDED,
            )
            .count()
        )
        if active_calls_count >= 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum number of active calls reached",
            )

        new_call = Call(
            caller_id=current_user.id,
            receiver_id=payload.receiver_id,
            call_type=payload.call_type,
            status=CallStatus.PENDING,
            encryption_key=generate_encryption_key(),
            last_key_update=datetime.now(timezone.utc),
        )
        self.db.add(new_call)
        self.db.commit()
        self.db.refresh(new_call)

        await notification_backend.send_real_time_notification(
            receiver.id,
            f"Incoming {payload.call_type} call from {getattr(current_user, 'username', current_user.email)}",
        )

        return new_call

    async def update_call_status(
        self,
        *,
        call_id: int,
        payload: schemas.CallUpdate,
        current_user: User,
    ) -> Call:
        call = self.db.query(Call).filter(Call.id == call_id).first()
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
            )
        if current_user.id not in [call.caller_id, call.receiver_id]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this call",
            )

        call.status = payload.status
        if payload.status == CallStatus.ENDED:
            call.end_time = datetime.now(timezone.utc)
            active_share = (
                self.db.query(ScreenShareSession)
                .filter(
                    ScreenShareSession.call_id == call.id,
                    ScreenShareSession.status == ScreenShareStatus.ACTIVE,
                )
                .first()
            )
            if active_share:
                active_share.status = ScreenShareStatus.ENDED
                active_share.end_time = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(call)
        return call

    def get_active_calls(self, *, current_user: User) -> list[Call]:
        return (
            self.db.query(Call)
            .filter(
                (Call.caller_id == current_user.id)
                | (Call.receiver_id == current_user.id),
                Call.status != CallStatus.ENDED,
            )
            .all()
        )

    def update_call_quality(self, *, call_id: int, quality_score: int) -> None:
        call = self.db.query(Call).filter(Call.id == call_id).first()
        if call:
            call.quality_score = quality_score
            self.db.commit()
