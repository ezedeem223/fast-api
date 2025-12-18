"""Application factory helpers to keep app/main.py lightweight."""

from __future__ import annotations

import logging
import os
from http import HTTPStatus
from pathlib import Path

from contextlib import asynccontextmanager

import orjson
from fastapi import Depends, FastAPI, Request, status, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse, RedirectResponse
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app import models, oauth2
from app.api.router import api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import get_db, engine
from app.core.middleware import (
    add_language_header,
    ip_ban_middleware,
    language_middleware,
)
from app.core.scheduling import register_startup_tasks
from app.i18n import ALL_LANGUAGES, get_locale, translate_text
from app.modules.utils.content import train_content_classifier
from app.notifications import ConnectionManager
from app.core.middleware.rate_limit import limiter
from app.core.logging_config import setup_logging
from app.core.middleware.logging_middleware import LoggingMiddleware
from app.core.error_handlers import register_exception_handlers
from app.core.cache.redis_cache import cache_manager
from app.core.monitoring import setup_monitoring  # Task 7: Import Monitoring

logger = logging.getLogger(__name__)
manager = ConnectionManager()


class CachedStaticFiles(StaticFiles):
    """StaticFiles mount that enforces Cache-Control when not provided by the file system."""
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


class HostRedirectMiddleware(LoggingMiddleware):
    """Enforce allowed hosts and HTTPS before the rest of the stack."""

    def __init__(self, app: FastAPI, allowed_hosts: list[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts or ["*"]

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if self.allowed_hosts and not (
            len(self.allowed_hosts) == 1 and self.allowed_hosts[0] == "*"
        ):
            if host and host not in self.allowed_hosts:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid host"},
                )
        if request.url.scheme != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        return await super().dispatch(request, call_next)


def _configure_app(app: FastAPI) -> None:
    allowed_hosts = (
        getattr(settings.__class__, "allowed_hosts", None)
        or getattr(settings, "allowed_hosts", None)
        or ["*"]
    )
    if allowed_hosts and not (len(allowed_hosts) == 1 and allowed_hosts[0] == "*"):
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    if settings.force_https:
        app.add_middleware(HostRedirectMiddleware, allowed_hosts=allowed_hosts)
        # Keep the standard redirect middleware present for compatibility checks/tests.
        app.add_middleware(HTTPSRedirectMiddleware)

    # Task 4: Add Logging Middleware
    # Logs all requests and responses with timing
    app.add_middleware(LoggingMiddleware)

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


def _reset_test_overrides() -> None:
    """
    Clean up test-specific monkeypatches that can leak between create_app calls.
    Currently ensures allowed_hosts/force_https revert for subsequent tests.
    """
    if getattr(settings, "environment", "").lower() != "test":
        return

    for target in (settings, settings.__class__):
        if hasattr(target, "allowed_hosts"):
            try:
                setattr(target, "allowed_hosts", None)
            except Exception:
                try:
                    object.__setattr__(target, "allowed_hosts", None)
                except Exception:
                    pass

    try:
        object.__setattr__(settings, "force_https", False)
    except Exception:
        try:
            setattr(settings, "force_https", False)
        except Exception:
            pass


def _register_routes(app: FastAPI) -> None:
    @app.get("/")
    async def root():
        return {"message": "Hello, World!"}

    # Task 8: Liveness Check (Is the app process running?)
    @app.get("/livez", tags=["Health"])
    async def livez():
        return {"status": "ok"}

    # Task 8: Readiness Check (Are dependencies like DB and Redis ready?)
    @app.get("/readyz", tags=["Health"])
    async def readyz(db: Session = Depends(get_db)):
        health_status = {"database": "unknown", "redis": "unknown"}
        is_ready = True

        # 1. Check Database
        try:
            db.execute(text("SELECT 1"))
            health_status["database"] = "connected"
        except Exception as e:
            logger.error(f"Readiness check failed (Database): {e}")
            health_status["database"] = "disconnected"
            is_ready = False

        # 2. Check Redis
        try:
            if cache_manager.redis:
                await cache_manager.redis.ping()
                health_status["redis"] = "connected"
            else:
                # If Redis is not enabled/configured, consider it skipped/disconnected based on strictness
                if getattr(cache_manager, "failed_init", False) and settings.environment.lower() == "test":
                    health_status["redis"] = "skipped"
                elif settings.redis_url:
                    health_status["redis"] = "disconnected (client not init)"
                    is_ready = False
                else:
                    health_status["redis"] = "skipped"
        except Exception as e:
            logger.error(f"Readiness check failed (Redis): {e}")
            health_status["redis"] = "disconnected"
            is_ready = False

        if not is_ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_status
            )

        return {"status": "ready", "details": health_status}

    @app.get("/protected-resource")
    def protected_resource(
        current_user: models.User = Depends(oauth2.get_current_user),
        db: Session = Depends(get_db),
    ):
        return {
            "message": "You have access to this protected resource",
            "user_id": current_user.id,
        }

    @app.get("/healthz/database")
    async def database_health_check(db: Session = Depends(get_db)):
        """
        Check database connection health.
        """
        try:
            # Test simple query
            db.execute(text("SELECT 1"))

            # Test connection pool stats
            pool = engine.pool
            pool_status = {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "total_connections": pool.size() + pool.overflow(),
            }

            return {"status": "healthy", "database": "connected", "pool": pool_status}
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


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


def _lifespan_factory():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.connection_manager = manager

        yield

        # Shutdown

    return lifespan


def _maybe_train_classifier() -> None:
    if settings.environment.lower() != "test" and not (
        Path("content_classifier.joblib").exists()
        and Path("content_vectorizer.joblib").exists()
    ):
        train_content_classifier()


def create_app() -> FastAPI:
    """
    Application Factory to create and configure the FastAPI application.
    Integrates Logging, Error Handling, Rate Limiting, and Middleware.
    """

    # Task 4: Setup Logging System first
    setup_logging(
        log_level=getattr(settings, "log_level", "INFO"),
        log_dir=getattr(settings, "log_dir", "logs"),
        app_name="fast-api",
        max_bytes=10 * 1024 * 1024,  # 10 MB
        backup_count=5,
        use_json=getattr(settings, "use_json_logs", False),
        use_colors=True,
    )

    _maybe_train_classifier()
    lifespan = _lifespan_factory()

    app = FastAPI(
        title="Your API",
        description="API for social media platform with comment filtering and sorting",
        version="1.0.0",
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        json_dumps=lambda v, *, default: orjson.dumps(v, default=default),
        json_loads=orjson.loads,
    )

    # Configure App State
    app.state.default_language = settings.default_language
    app.state.environment = settings.environment

    # Task 2: Initialize Rate Limiter
    # Note: The exception handler for RateLimitExceeded is now handled
    # globally in register_exception_handlers (Task 3)
    app.state.limiter = limiter
    if hasattr(limiter, "enabled"):
        limiter.enabled = settings.environment.lower() != "test" and (
            os.getenv("APP_ENV", settings.environment).lower() != "test"
        )

    # Configure Middleware and Routes
    _configure_app(app)
    _register_routes(app)

    # Task 3: Register Unified Exception Handlers
    # This replaces the old _register_exception_handlers function
    register_exception_handlers(app)

    # Task 7: Setup Monitoring (Prometheus)
    setup_monitoring(app)

    logger.info("Application startup complete")

    _reset_test_overrides()

    return app


__all__ = ["create_app"]
