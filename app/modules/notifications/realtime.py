"""WebSocket connection management for real-time notifications."""

from __future__ import annotations

import asyncio
from typing import Dict, List, Union

from fastapi import WebSocket

from .common import handle_async_errors, logger


class ConnectionManager:
    """Tracks active WebSocket connections per user and broadcast helpers."""

    def __init__(self) -> None:
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Accept and register a WebSocket connection for a given user."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            logger.info("WebSocket connected for user %s", user_id)

    async def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        """Remove a WebSocket connection belonging to a user if present."""
        async with self._lock:
            if (
                user_id in self.active_connections
                and websocket in self.active_connections[user_id]
            ):
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logger.info("WebSocket disconnected for user %s", user_id)

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

    async def broadcast(self, message: dict) -> None:
        """Send a message to every connected user."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


@handle_async_errors
async def send_real_time_notification(user_id: int, message: Union[str, dict]) -> None:
    """Send a WebSocket notification to a specific user."""
    payload = (
        {"message": message, "type": "simple_notification"}
        if isinstance(message, str)
        else message
    )
    await manager.send_personal_message(payload, user_id)
    logger.info("Real-time notification sent to user %s", user_id)


__all__ = ["ConnectionManager", "manager", "send_real_time_notification"]
