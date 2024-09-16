from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import models
from .database import engine, get_db
from .routers import (
    post,
    user,
    auth,
    comment,
    follow,
    block,
    admin_dashboard,
    oauth,
    search,
    message,
    community,
    p2fa,
)
from .routers.vote import router as vote_router
from .config import settings
from .notifications import (
    ConnectionManager,
    send_real_time_notification,
)
from .oauth2 import get_current_user  # استيراد للتحقق من المستخدم

app = FastAPI()

# CORS settings
origins = [
    "https://example.com",
    "https://www.example.com",
    # Add your trusted domains here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote_router)
app.include_router(comment.router)
app.include_router(follow.router)
app.include_router(block.router)
app.include_router(admin_dashboard.router)
app.include_router(oauth.router)
app.include_router(search.router)
app.include_router(message.router)
app.include_router(community.router)
app.include_router(p2fa.router)

manager = ConnectionManager()


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                raise ValueError("Received empty message")
            await send_real_time_notification(websocket, user_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        print(f"Client #{user_id} disconnected")
    except Exception as e:
        print(f"An error occurred: {e}")
        await manager.disconnect(websocket)


# حماية المسار المحمي باستخدام توثيق JWT
@app.get("/protected-resource")
def protected_resource(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return {
        "message": "You have access to this protected resource",
        "user_id": current_user.id,
    }
