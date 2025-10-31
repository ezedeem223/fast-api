"""Application entry point and FastAPI factory.

The previous version of this module executed a substantial amount of work at
import time (model training, background schedulers, Celery configuration,
Firebase initialisation, etc.).  That approach made the service extremely hard
to run in constrained environments and completely broke automated tests when the
required infrastructure was not available.  The rewritten module embraces an
application factory pattern: the FastAPI instance is created lazily and heavy
integrations are only enabled when explicitly requested via configuration.
"""

from __future__ import annotations

import logging
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import models, oauth2
from .config import settings
from .database import SessionLocal, get_db
from .i18n import ALL_LANGUAGES, get_locale, translate_text
from .middleware.language import language_middleware
from .notifications import manager as notification_manager, send_real_time_notification
from .utils import (
    create_default_categories,
    get_client_ip,
    is_ip_banned,
    train_content_classifier,
    update_search_vector,
)

logger = logging.getLogger(__name__)
manager = notification_manager


def _include_routers(application: FastAPI) -> None:
    """Import routers lazily to avoid mandatory heavy dependencies during tests."""

    try:
        from .routers import (
            admin_dashboard,
            amenhotep,
            auth,
            banned_words,
            block,
            business,
            call,
            category_management,
            comment,
            community,
            follow,
            insights,
            hashtag,
            message,
            moderation,
            oauth,
            p2fa,
            post,
            reaction,
            screen_share,
            search,
            session,
            social_auth,
            statistics,
            sticker,
            support,
            user,
            vote,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Unable to load routers: %s", exc)
        raise

    routers = [
        post.router,
        user.router,
        auth.router,
        vote.router,
        comment.router,
        follow.router,
        block.router,
        admin_dashboard.router,
        oauth.router,
        search.router,
        message.router,
        community.router,
        p2fa.router,
        moderation.router,
        support.router,
        business.router,
        sticker.router,
        call.router,
        insights.router,
        screen_share.router,
        session.router,
        hashtag.router,
        reaction.router,
        statistics.router,
        banned_words.router,
        category_management.router,
        social_auth.router,
        amenhotep.router,
    ]

    for router in routers:
        application.include_router(router)


def _register_cors(application: FastAPI) -> None:
    origins = [
        "https://example.com",
        "https://www.example.com",
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _configure_middlewares(application: FastAPI) -> None:
    application.middleware("http")(language_middleware)

    @application.middleware("http")
    async def check_ip_ban(request: Request, call_next):
        db = next(get_db())
        client_ip = get_client_ip(request)
        if is_ip_banned(db, client_ip):
            return JSONResponse(status_code=403, content={"detail": "Your IP address is banned"})
        return await call_next(request)

    @application.middleware("http")
    async def add_language_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Language"] = get_locale(request)
        return response


def _register_routes(application: FastAPI) -> None:
    @application.get("/")
    async def root():
        return {"message": "Welcome to our application"}

    @application.get("/languages")
    def get_available_languages():
        return ALL_LANGUAGES

    @application.post("/translate")
    async def translate_content(request: Request):
        data = await request.json()
        text = data.get("text", "")
        source_lang = data.get("source_lang", get_locale(request))
        target_lang = data.get("target_lang", application.state.default_language)
        translated = translate_text(text, source_lang, target_lang)
        return {
            "translated": translated,
            "source_lang": source_lang,
            "target_lang": target_lang,
        }

    @application.get("/protected-resource")
    def protected_resource(current_user: models.User = Depends(oauth2.get_current_user), db=Depends(get_db)):
        return {
            "message": "You have access to this protected resource",
            "user_id": current_user.id,
        }

    @application.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: int):
        await manager.connect(websocket, user_id)
        try:
            while True:
                data = await websocket.receive_text()
                if not data:
                    raise ValueError("Received empty message")
                await send_real_time_notification(user_id, data)
        except WebSocketDisconnect:
            await manager.disconnect(websocket, user_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("WebSocket error: %s", exc)
            await manager.disconnect(websocket, user_id)


def _register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error("ValidationError for request %s: %s", request.url.path, exc.errors())
        return JSONResponse(status_code=422, content={"detail": exc.errors()})


def _register_startup(application: FastAPI) -> None:
    @application.on_event("startup")
    async def startup_event():
        if settings.testing:
            return
        db = SessionLocal()
        try:
            create_default_categories(db)
        finally:
            db.close()

        try:
            train_content_classifier()
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Content classifier training failed: %s", exc)

        update_search_vector()

        logger.info("Startup tasks completed")


def create_application() -> FastAPI:
    application = FastAPI(
        title="Your API",
        description="API for social media platform with comment filtering and sorting",
        version="1.0.0",
    )
    application.state.default_language = settings.default_language

    _register_cors(application)
    _configure_middlewares(application)
    _register_routes(application)
    _register_exception_handlers(application)
    _register_startup(application)

    if not settings.testing:
        _include_routers(application)

    return application


app = create_application()
