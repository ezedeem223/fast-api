"""WebSocket connection management for real-time notifications."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from fastapi import WebSocket, status

from app.core.cache.redis_cache import cache_manager
from .common import logger


class ConnectionManager:
    """Tracks active WebSocket connections per user and broadcast helpers.

    The manager keeps a local registry *and* mirrors lightweight presence data
    into Redis when available so multi-instance deployments can reason about
    active socket counts. A small per-user connection limit prevents runaway
    socket creation from a single client.
    """

    def __init__(
        self,
        *,
        max_connections_per_user: int = 5,
        registry_ttl: int = 600,
    ) -> None:
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_counts: Dict[int, int] = {}
        self.last_disconnect_reason: Dict[int, str] = {}
        self._connection_ids: Dict[int, set[str]] = {}
        self._reverse_index: Dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
        self.max_connections_per_user = max_connections_per_user
        self.registry_ttl = registry_ttl

    async def connect(self, websocket: WebSocket, user_id: int) -> bool:
        """Accept and register a WebSocket connection for a given user."""
        await websocket.accept()
        async with self._lock:
            slots = self.active_connections.setdefault(user_id, [])
            if len(slots) >= self.max_connections_per_user:
                # Enforce per-user connection cap to protect the server.
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="socket limit exceeded",
                )
                self.last_disconnect_reason[user_id] = "limit_exceeded"
                logger.warning(
                    "WebSocket connection rejected for user %s (limit=%s)",
                    user_id,
                    self.max_connections_per_user,
                )
                return False

            slots.append(websocket)
            self.connection_counts[user_id] = len(slots)
            connection_id = self._make_connection_id(websocket, user_id)
            self._connection_ids.setdefault(user_id, set()).add(connection_id)
            self._reverse_index[websocket] = connection_id
            logger.info(
                "WebSocket connected for user %s (connections=%s)",
                user_id,
                self.connection_counts[user_id],
            )

        await self._sync_presence(user_id)
        return True

    async def disconnect(
        self,
        websocket: WebSocket,
        user_id: int,
        *,
        reason: str = "client_disconnected",
    ) -> None:
        """Remove a WebSocket connection belonging to a user if present."""
        async with self._lock:
            slots = self.active_connections.get(user_id, [])
            if websocket in slots:
                slots.remove(websocket)
                if not slots:
                    self.active_connections.pop(user_id, None)
                self.connection_counts[user_id] = len(slots)
            connection_id = self._reverse_index.pop(websocket, None)
            if connection_id:
                conn_set = self._connection_ids.get(user_id, set())
                conn_set.discard(connection_id)
                if not conn_set:
                    self._connection_ids.pop(user_id, None)
            self.last_disconnect_reason[user_id] = reason
            logger.info(
                "WebSocket disconnected for user %s (reason=%s, remaining=%s)",
                user_id,
                reason,
                self.connection_counts.get(user_id, 0),
            )

        await self._sync_presence(user_id, reason=reason)

    async def send_personal_message(self, message: dict, user_id: int) -> None:
        """Send a payload to all active WebSocket connections of a user."""
        if user_id not in self.active_connections:
            return

        broken_connections: List[WebSocket] = []
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Error sending message to user %s: %s", user_id, exc)
                broken_connections.append(connection)

        if not broken_connections:
            return

        async with self._lock:
            for connection in broken_connections:
                if (
                    user_id in self.active_connections
                    and connection in self.active_connections[user_id]
                ):
                    self.active_connections[user_id].remove(connection)
                    self._reverse_index.pop(connection, None)
            self.connection_counts[user_id] = len(
                self.active_connections.get(user_id, [])
            )

        await self._sync_presence(user_id, reason="send_failure_cleanup")

    async def broadcast(self, message: dict) -> None:
        """Send a message to every connected user."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    async def _sync_presence(self, user_id: int, *, reason: Optional[str] = None):
        """Mirror lightweight presence state to Redis for observability."""
        if not cache_manager.enabled or not cache_manager.redis:
            return
        try:
            payload = {
                "count": self.connection_counts.get(user_id, 0),
                "connections": sorted(self._connection_ids.get(user_id, set())),
                "last_disconnect_reason": reason or self.last_disconnect_reason.get(
                    user_id
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await cache_manager.set_with_tags(
                f"realtime:sockets:{user_id}",
                payload,
                tags=["realtime:sockets", f"user:{user_id}"],
                ttl=self.registry_ttl,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to mirror socket registry for user %s: %s", user_id, exc)

    def metrics(self) -> dict:
        """Return a snapshot suitable for logging/metrics exporters."""
        return {
            "active_users": len(self.active_connections),
            "connection_counts": dict(self.connection_counts),
            "last_disconnect_reason": dict(self.last_disconnect_reason),
        }

    def _make_connection_id(self, websocket: WebSocket, user_id: int) -> str:
        """Create a deterministic connection identifier."""
        return f"{user_id}:{id(websocket)}"


manager = ConnectionManager()


async def send_real_time_notification(user_id: int, message: Union[str, dict]) -> None:
    """Send a WebSocket notification to a specific user."""
    payload = (
        {"message": message, "type": "simple_notification"}
        if isinstance(message, str)
        else message
    )
    try:
        await manager.send_personal_message(payload, user_id)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error sending notification to user %s: %s", user_id, exc)
        raise
    logger.info("Real-time notification sent to user %s", user_id)


__all__ = ["ConnectionManager", "manager", "send_real_time_notification"]
