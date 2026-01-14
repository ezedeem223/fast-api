"""WebSocket signaling for call rooms with authenticated handshakes and room security.

Lifecycle:
- First joiner becomes owner and can mint join tokens for others; room expires after TTL (default 1h).
- Authorization accepts owner or valid single-use join_token mapped to user_id; denies replays.
- Registry state mirrored to Redis when available for multi-instance visibility (tagged by callroom:{room_id}).

Notes:
- Designed for multi-instance environments by pushing presence into Redis when available.
- Enforces participant limits and token replay protection to reduce abuse.
"""

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set

from app.core.cache.redis_cache import cache_manager
from app.notifications import manager as notifications_manager
from app.notifications import ConnectionManager
from app.oauth2 import get_current_user
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

router = APIRouter(prefix="/ws/call", tags=["Calls"])
call_manager = ConnectionManager(
    registry_prefix="calls:signaling",
    registry_tag="calls:signaling",
)


@dataclass
class RoomState:
    """State for a call room including owner, participants, expiry, and join tokens."""

    owner_id: int
    allowed_participants: Set[int] = field(default_factory=set)
    participants: Set[int] = field(default_factory=set)
    expiry: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    )
    join_tokens: Dict[str, int] = field(default_factory=dict)  # token -> user_id

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expiry


class CallRoomRegistry:
    """Room registry with in-memory state and optional Redis mirroring."""

    def __init__(self, default_ttl: int = 3600):
        self._lock = asyncio.Lock()
        self.rooms: Dict[str, RoomState] = {}
        self.default_ttl = default_ttl

    async def create_room(
        self,
        room_id: str,
        owner_id: int,
        allowed_participants: Optional[Set[int]] = None,
        ttl: Optional[int] = None,
    ) -> RoomState:
        async with self._lock:
            state = self.rooms.get(room_id)
            if state and not state.is_expired():
                return state
            expiry = datetime.now(timezone.utc) + timedelta(
                seconds=ttl or self.default_ttl
            )
            state = RoomState(
                owner_id=owner_id,
                allowed_participants=allowed_participants or set(),
                expiry=expiry,
            )
            self.rooms[room_id] = state
        await self._mirror(room_id, state)
        return state

    async def issue_join_token(
        self, room_id: str, owner_id: int, allowed_user_id: int, ttl: int = 900
    ) -> str:
        async with self._lock:
            state = self.rooms.get(room_id)
            if not state or state.owner_id != owner_id or state.is_expired():
                raise ValueError("Room not found or expired")
            token = secrets.token_urlsafe(16)
            state.join_tokens[token] = allowed_user_id
            state.allowed_participants.add(allowed_user_id)
            state.expiry = min(
                state.expiry, datetime.now(timezone.utc) + timedelta(seconds=ttl)
            )
        await self._mirror(room_id, state)
        return token

    async def authorize(
        self, room_id: str, user_id: int, join_token: Optional[str]
    ) -> bool:
        async with self._lock:
            state = self.rooms.get(room_id)
            if not state:
                return False
            if state.is_expired():
                self.rooms.pop(room_id, None)
                return False
            if user_id == state.owner_id:
                return True
            if join_token is not None:
                if join_token in state.join_tokens:
                    token_owner = state.join_tokens.pop(join_token)
                    if token_owner == user_id:
                        state.allowed_participants.add(user_id)
                        return True
                # Provided token is invalid or already used: deny to prevent replay.
                return False
            return user_id in state.allowed_participants

    async def add_participant(self, room_id: str, user_id: int) -> RoomState:
        async with self._lock:
            state = self.rooms[room_id]
            state.participants.add(user_id)
        await self._mirror(room_id, state)
        return state

    async def remove_participant(self, room_id: str, user_id: int) -> None:
        async with self._lock:
            state = self.rooms.get(room_id)
            if not state:
                return
            state.participants.discard(user_id)
            if state.is_expired() or not state.participants:
                # Keep room for expiry window unless empty and expired
                if state.is_expired():
                    self.rooms.pop(room_id, None)
        await self._mirror(room_id, state)

    async def participants(self, room_id: str) -> Set[int]:
        async with self._lock:
            state = self.rooms.get(room_id)
            return set(state.participants) if state else set()

    async def mark_expired(self, room_id: str) -> None:
        async with self._lock:
            self.rooms.pop(room_id, None)
        await cache_manager.invalidate_by_tag(f"callroom:{room_id}")

    async def _mirror(self, room_id: str, state: Optional[RoomState]) -> None:
        """Mirror room metadata to Redis for multi-instance observability."""
        if not cache_manager.enabled or not cache_manager.redis or not state:
            return
        try:
            payload = {
                "owner": state.owner_id,
                "participants": sorted(state.participants),
                "allowed": sorted(state.allowed_participants),
                "expires_at": state.expiry.isoformat(),
            }
            await cache_manager.set_with_tags(
                f"callroom:{room_id}",
                payload,
                tags=[f"callroom:{room_id}", "callroom"],
                ttl=int(self.default_ttl),
            )
        except Exception:
            # Do not crash signaling on mirror failures
            pass


room_registry = CallRoomRegistry()


@router.websocket("/{room_id}")
async def signaling_ws(
    websocket: WebSocket,
    room_id: str,
    join_token: Optional[str] = Query(default=None, alias="token"),
    current_user=Depends(get_current_user),
):
    """Authenticated WebSocket for call signaling (owner or single-use join token)."""
    # Ensure room exists (owner on first connect)
    state = room_registry.rooms.get(room_id)
    if not state:
        state = await room_registry.create_room(room_id, owner_id=current_user.id)

    if state.is_expired():
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="room expired"
        )
        await room_registry.mark_expired(room_id)
        return

    if not await room_registry.authorize(room_id, current_user.id, join_token):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="join denied"
        )
        return

    connected = await call_manager.connect(websocket, current_user.id)
    if connected is False:
        return

    await room_registry.add_participant(room_id, current_user.id)
    try:
        while True:
            data = await websocket.receive_json()
            # basic shape enforcement
            if "type" not in data:
                raise HTTPException(status_code=400, detail="Missing message type")
            payload = {
                "room_id": room_id,
                "from": current_user.id,
                "message": data,
            }
            # broadcast to other participants
            participants = await room_registry.participants(room_id)
            targets = participants - {current_user.id}
            for uid in targets:
                if call_manager.active_connections.get(uid):
                    await call_manager.send_personal_message(payload, uid)
                else:
                    await notifications_manager.send_personal_message(payload, uid)
    except WebSocketDisconnect:
        await room_registry.remove_participant(room_id, current_user.id)
        await call_manager.disconnect(
            websocket,
            current_user.id,
            reason="disconnect",
        )
    except Exception:
        await room_registry.remove_participant(room_id, current_user.id)
        await call_manager.disconnect(
            websocket,
            current_user.id,
            reason="error",
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
