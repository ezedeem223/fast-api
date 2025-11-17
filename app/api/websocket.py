"""WebSocket endpoints for real-time notifications."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.notifications import ConnectionManager, send_real_time_notification

router = APIRouter()
manager = ConnectionManager()


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
    except Exception:
        await manager.disconnect(websocket, user_id)


__all__ = ["router"]
