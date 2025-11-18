"""Application factory helpers to keep app/main.py lightweight."""

from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import models, oauth2
from app.api.router import api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import get_db
from app.core.middleware import add_language_header, ip_ban_middleware, language_middleware
from app.core.scheduling import register_startup_tasks
from app.i18n import ALL_LANGUAGES, get_locale, translate_text
from app.modules.utils.content import train_content_classifier
from app.notifications import ConnectionManager
from app.routers import community

logger = logging.getLogger(__name__)
manager = ConnectionManager()

ERROR_MESSAGE_OVERRIDES = {
    "\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0627\u0639\u062a\u0645\u0627\u062f \u063a\u064a\u0631 \u0635\u0627\u0644\u062d\u0629": "Invalid Credentials",
    "\u0627\u0644\u062d\u0633\u0627\u0628 \u0645\u0648\u0642\u0648\u0641": "Account is suspended",
    "\u062a\u0645 \u0642\u0641\u0644 \u0627\u0644\u062d\u0633\u0627\u0628. \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649 \u0644\u0627\u062d\u0642\u0627\u064b": "Account locked. Please try again later.",
}


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, cache_control: str | None = None, **kwargs):
        self._cache_control = cache_control
        super().__init__(*args, **kwargs)

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if (
            self._cache_control
            and response.status_code == HTTPStatus.OK
            and "cache-control" not in response.headers
        ):
            response.headers["Cache-Control"] = self._cache_control
        return response


def _configure_app(app: FastAPI) -> None:
    if settings.force_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    allowed_hosts = getattr(settings, "allowed_hosts", ["*"])
    if allowed_hosts and not (len(allowed_hosts) == 1 and allowed_hosts[0] == "*"):
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    origins = settings.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(websocket_router)
    app.middleware("http")(language_middleware)
    app.middleware("http")(add_language_header)
    app.middleware("http")(ip_ban_middleware)
    _mount_static_files(app)
    register_startup_tasks(app)


def _register_routes(app: FastAPI) -> None:
    @app.get("/")
    async def root():
        return {"message": "Hello, World!"}

    @app.get("/livez", tags=["Health"])
    async def livez():
        return {"status": "ok"}

    @app.get("/readyz", tags=["Health"])
    def readyz(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/protected-resource")
    def protected_resource(
        current_user: models.User = Depends(oauth2.get_current_user),
        db: Session = Depends(get_db),
    ):
        return {
            "message": "You have access to this protected resource",
            "user_id": current_user.id,
        }


def _mount_static_files(app: FastAPI) -> None:
    try:
        static_dir = Path(settings.static_root)
        uploads_dir = Path(settings.uploads_root)
    except Exception:
        # Fallback to working directory if settings paths are invalid
        static_dir = Path("static")
        uploads_dir = Path("uploads")

    static_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/static",
        CachedStaticFiles(
            directory=static_dir,
            check_dir=False,
            cache_control=settings.static_cache_control,
        ),
        name="static",
    )
    app.mount(
        "/uploads",
        CachedStaticFiles(
            directory=uploads_dir,
            check_dir=False,
            cache_control=settings.uploads_cache_control,
        ),
        name="uploads",
    )

    @app.get("/languages")
    def get_available_languages():
        return ALL_LANGUAGES

    @app.post("/translate")
    async def translate_content(request: Request):
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


def _register_exception_handlers(app: FastAPI) -> None:
    http_422 = getattr(
        status, "HTTP_422_UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error("ValidationError for request: %s", request.url.path)
        logger.error("Error details: %s", exc.errors())

        if request.url.path == "/communities/user-invitations":
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
                logger.error("HTTP Exception in user-invitations: %s", he)
                return JSONResponse(
                    status_code=he.status_code, content={"detail": he.detail}
                )
            except Exception as err:
                logger.exception("Error handling user-invitations: %s", err)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Internal server error"},
                )

        if request.url.path.startswith("/communities"):
            path_segments = request.url.path.split("/")
            if len(path_segments) > 2 and path_segments[2].isdigit():
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "Community not found"},
                )

        return JSONResponse(
            status_code=http_422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            detail = ERROR_MESSAGE_OVERRIDES.get(detail, detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=exc.headers,
        )


def _lifespan_factory():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.connection_manager = manager
        yield

    return lifespan

def _maybe_train_classifier() -> None:
    if (
        settings.environment.lower() != "test"
        and not (
            Path("content_classifier.joblib").exists()
            and Path("content_vectorizer.joblib").exists()
        )
    ):
        train_content_classifier()


def create_app() -> FastAPI:
    _maybe_train_classifier()
    lifespan = _lifespan_factory()
    app = FastAPI(
        title="Your API",
        description="API for social media platform with comment filtering and sorting",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.default_language = settings.default_language
    _configure_app(app)
    _register_routes(app)
    _register_exception_handlers(app)
    return app


__all__ = ["create_app"]
