"""WebSocket endpoints for real-time notifications."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.notifications import ConnectionManager, send_real_time_notification

router = APIRouter()
manager = ConnectionManager()
logger = logging.getLogger(__name__)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """Handle websocket connections for notification streaming."""
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                raise ValueError("Received empty message")
            await send_real_time_notification(user_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)
        logger.info("WebSocket disconnected for user_id=%s", user_id)
    except Exception as exc:
        logger.exception("WebSocket error for user_id=%s: %s", user_id, exc)
        await manager.disconnect(websocket, user_id)


__all__ = ["router"]
