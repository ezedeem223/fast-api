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
from . import models, oauth2
from .database import engine, get_db, SessionLocal
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
    moderator,
)
from .config import settings
from .notifications import ConnectionManager, send_real_time_notification
from apscheduler.schedulers.background import BackgroundScheduler

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
    logger.error(f"ValidationError for request: {request.url.path}")
    logger.error(f"Error details: {exc.errors()}")

    if request.url.path == "/communities/user-invitations":
        logger.info("Handling user-invitations request")
        try:
            db = next(get_db())
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header",
                )
            token = auth_header.split(" ")[1]
            current_user = oauth2.get_current_user(token, db)
            return await community.get_user_invitations(request, db, current_user)
        except HTTPException as he:
            logger.error(f"HTTP Exception in user-invitations: {str(he)}")
            return JSONResponse(
                status_code=he.status_code, content={"detail": he.detail}
            )
        except Exception as e:
            logger.error(f"Error handling user-invitations: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )

    if request.url.path.startswith("/communities"):
        logger.info(f"Community-related request: {request.url.path}")
        path_segments = request.url.path.split("/")
        logger.info(f"Path segments: {path_segments}")

        if len(path_segments) > 2 and path_segments[2].isdigit():
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
app.include_router(moderator.router)

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
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "message": "You have access to this protected resource",
        "user_id": current_user.id,
    }


# New function to update all communities statistics
def update_all_communities_statistics():
    db = SessionLocal()
    try:
        communities = db.query(models.Community).all()
        for community in communities:
            community.router.update_community_statistics(db, community.id)
    finally:
        db.close()


# Initialize and start the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(update_all_communities_statistics, "cron", hour=0)
scheduler.start()


# Shutdown event to stop the scheduler when the app shuts down
@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
