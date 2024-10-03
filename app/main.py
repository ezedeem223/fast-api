import logging
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
    vote,
)
from .config import settings
from .notifications import ConnectionManager, send_real_time_notification
from .oauth2 import get_current_user

logger = logging.getLogger(__name__)

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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/communities"):
        # Проверяем, является ли это запросом на создание контента
        if any(segment.isdigit() for segment in request.url.path.split("/")):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "Community not found"},
            )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


# Include routers
app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote.router)
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


@app.get("/protected-resource")
def protected_resource(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return {
        "message": "You have access to this protected resource",
        "user_id": current_user.id,
    }
