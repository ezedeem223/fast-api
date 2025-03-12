import logging
from pathlib import Path  # Used for file path operations
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
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi_utils.tasks import repeat_every
import gettext

# Import custom modules and routers
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
    support,
    business,
    sticker,
    call,
    screen_share,
    session,
    hashtag,
    reaction,
    statistics,
    banned_words,
    moderation,
    category_management,
    social_auth,
    amenhotep,
    social_posts,
)
from .config import settings
from .notifications import (
    ConnectionManager,
    send_real_time_notification,
    NotificationService,
)  # Added NotificationService
from app.utils import train_content_classifier, create_default_categories
from .celery_worker import celery_app
from .analytics import model, tokenizer, clean_old_statistics
from app.routers.search import update_search_suggestions
from .utils import (
    update_search_vector,
    spell,
    update_post_score,
    get_client_ip,
    is_ip_banned,
)
from .i18n import babel, ALL_LANGUAGES, get_locale, translate_text
from .middleware.language import language_middleware
from .firebase_config import initialize_firebase
from .ai_chat.amenhotep import AmenhotepAI

# Configure logging and initial settings
logger = logging.getLogger(__name__)
train_content_classifier()  # Train content classifier on startup
app = FastAPI(
    title="Your API",
    description="API for social media platform with comment filtering and sorting",
    version="1.0.0",
)
app.state.default_language = settings.default_language

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

# Internationalization setup
localedir = "locales"
translation = gettext.translation("messages", localedir, fallback=True)
_ = translation.gettext

# Include routers (all endpoints are registered here)
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
app.include_router(support.router)
app.include_router(business.router)
app.include_router(sticker.router)
app.include_router(call.router)
app.include_router(screen_share.router)
app.include_router(session.router)
app.include_router(hashtag.router)
app.include_router(reaction.router)
app.include_router(statistics.router)
app.include_router(banned_words.router)  # Assuming banned_words is a valid router
app.include_router(moderation.router)
app.include_router(category_management.router)
app.include_router(social_auth.router)
app.include_router(amenhotep.router)
# app.include_router(social_posts.router)

# Add language middleware to all HTTP requests
app.middleware("http")(language_middleware)

# Initialize WebSocket connection manager
manager = ConnectionManager()


# Root endpoint (only one definition to avoid conflicts)
@app.get("/")
async def root():
    """
    English Explanation: Returns a welcome message to the application.
    """
    return {"message": _("Welcome to our application")}


# Exception handler for request validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    English Explanation: Handles request validation errors with proper logging and response.
    """
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


# WebSocket endpoint for real-time notifications
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    English Explanation: Handles WebSocket connections for real-time messaging.
    """
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


# Startup event to execute initial configuration tasks
@app.on_event("startup")
async def startup_event():
    """
    English Explanation: Executes startup tasks such as creating default categories,
    updating search vectors, initializing services, and loading the content analysis model.
    """
    db = SessionLocal()
    create_default_categories(db)
    db.close()
    update_search_vector()
    # Ensure the Path module is available for constructing file paths
    arabic_words_path = Path(__file__).parent / "arabic_words.txt"
    app.state.amenhotep = AmenhotepAI()
    spell.word_frequency.load_dictionary(str(arabic_words_path))
    celery_app.conf.beat_schedule = {
        "check-scheduled-posts": {
            "task": "app.celery_worker.schedule_post_publication",
            "schedule": 60.0,  # every minute
        },
    }
    print("Loading content analysis model...")
    model.eval()
    print("Content analysis model loaded successfully!")
    if not initialize_firebase():
        logger.warning(
            "Firebase initialization failed - push notifications will be disabled"
        )


# Middleware to check if the client's IP is banned
@app.middleware("http")
async def check_ip_ban(request: Request, call_next):
    """
    English Explanation: Blocks requests from banned IP addresses.
    """
    db = next(get_db())
    client_ip = get_client_ip(request)
    if is_ip_banned(db, client_ip):
        return JSONResponse(
            status_code=403, content={"detail": "Your IP address is banned"}
        )
    response = await call_next(request)
    return response


# Protected endpoint that requires authentication
@app.get("/protected-resource")
def protected_resource(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    English Explanation: Returns a protected resource accessible only to authenticated users.
    """
    return {
        "message": "You have access to this protected resource",
        "user_id": current_user.id,
    }


# Function to update statistics for all communities
def update_all_communities_statistics():
    """
    English Explanation: Iterates through all communities and updates their statistics.
    """
    db = SessionLocal()
    try:
        communities = db.query(models.Community).all()
        for community in communities:
            # Assuming update_community_statistics is implemented in the community router
            community.router.update_community_statistics(db, community.id)
    finally:
        db.close()


# Create a single scheduler instance and add all scheduled jobs
scheduler = BackgroundScheduler()
scheduler.add_job(clean_old_statistics, "cron", hour=0, args=[next(get_db())])
scheduler.add_job(update_all_communities_statistics, "cron", hour=0)  # Defined below
scheduler.start()


# Shutdown event to gracefully stop the scheduler when the app shuts down
@app.on_event("shutdown")
def shutdown_event():
    """
    English Explanation: Shuts down the scheduler on application shutdown.
    """
    scheduler.shutdown()


# Scheduled task: Update search suggestions daily
@app.on_event("startup")
@repeat_every(seconds=60 * 60 * 24)  # every 24 hours
def update_search_suggestions_task():
    """
    English Explanation: Updates search suggestions once a day.
    """
    db = next(get_db())
    update_search_suggestions(db)


# Scheduled task: Update post scores hourly
@app.on_event("startup")
@repeat_every(seconds=60 * 60)  # every hour
def update_all_post_scores():
    """
    English Explanation: Recalculates and updates the scores for all posts every hour.
    """
    db = SessionLocal()
    try:
        posts = db.query(models.Post).all()
        for post in posts:
            update_post_score(db, post)
    finally:
        db.close()


# Middleware to add the 'Content-Language' header to all responses
@app.middleware("http")
async def add_language_header(request: Request, call_next):
    """
    English Explanation: Adds the Content-Language header based on the request's locale.
    """
    response = await call_next(request)
    lang = get_locale(request)
    response.headers["Content-Language"] = lang
    return response


# Endpoint to retrieve all available languages (single definition)
@app.get("/languages")
def get_available_languages():
    """
    English Explanation: Returns a list of supported languages.
    """
    return ALL_LANGUAGES


# Endpoint to translate content from one language to another
@app.post("/translate")
async def translate_content(request: Request):
    """
    English Explanation: Translates provided text using source and target languages.
    """
    data = await request.json()
    text = data.get("text")
    source_lang = data.get("source_lang", get_locale(request))
    target_lang = data.get("target_lang", app.state.default_language)
    translated = translate_text(text, source_lang, target_lang)
    return {
        "translated": translated,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }


# Scheduled task: Clean up notifications older than 30 days daily
@app.on_event("startup")
@repeat_every(seconds=86400)  # every 24 hours
def cleanup_old_notifications():
    """
    English Explanation: Removes notifications older than 30 days.
    """
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        notification_service.cleanup_old_notifications(30)
    finally:
        db.close()


# Scheduled task: Retry failed notifications every hour (up to 3 attempts)
@app.on_event("startup")
@repeat_every(seconds=3600)  # every hour
def retry_failed_notifications():
    """
    English Explanation: Attempts to resend notifications that previously failed.
    """
    db = SessionLocal()
    try:
        notifications = (
            db.query(models.Notification)
            .filter(
                models.Notification.status == models.NotificationStatus.FAILED,
                models.Notification.retry_count < 3,
            )
            .all()
        )
        notification_service = NotificationService(db)
        for notification in notifications:
            notification_service.retry_failed_notification(notification.id)
    finally:
        db.close()
