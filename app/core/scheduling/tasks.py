"""Centralised scheduling and startup task registration.

- Registers startup handlers (search suggestions, post scores, notifications cleanup/retry).
- Configures APScheduler in non-test environments with cron jobs for statistics/communities.
- Guards repeat_every tasks in tests to avoid lingering background tasks.
- Ensures Firebase/search setup happens once at startup in non-test environments.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi_utils.tasks import repeat_every

from app import models
from app.ai_chat.amenhotep import get_shared_amenhotep
from app.analytics import clean_old_statistics, model
from app.celery_worker import celery_app
from app.core.cache.redis_cache import cache_manager
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.firebase_config import initialize_firebase
from app.modules.community import Community
from app.modules.search.service import update_search_suggestions
from app.modules.utils.analytics import create_default_categories, update_post_score
from app.modules.utils.search import spell, update_search_vector
from app.notifications import NotificationService
from app.services.reels import ReelService
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _run_async_blocking(awaitable):
    """Execute an awaitable from sync contexts, creating an event loop when none exists."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(awaitable)


def _is_test_env() -> bool:
    """Helper for  is test env."""
    return (
        settings.environment.lower() == "test"
        or os.getenv("APP_ENV", "").lower() == "test"
        or os.getenv("PYTEST_CURRENT_TEST") is not None
    )


async def _prewarm_amenhotep(app: FastAPI) -> None:
    """Warm Amenhotep AI in the background to reduce first-response latency."""
    try:
        await get_shared_amenhotep(app)
    except Exception as exc:  # pragma: no cover - defensive log
        logger.warning("Amenhotep AI prewarm failed: %s", exc)


def _maybe_repeat_every(**kwargs):
    """Apply repeat_every only outside test env to avoid lingering background tasks in tests."""

    def decorator(fn):
        is_async = inspect.iscoroutinefunction(fn)
        scheduled = repeat_every(**kwargs)(fn)

        if is_async:

            async def wrapper(*args, **kws):
                if _is_test_env():
                    return None
                return await scheduled(*args, **kws)

        else:

            def wrapper(*args, **kws):
                if _is_test_env():
                    return None
                return scheduled(*args, **kws)

        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper

    return decorator


def register_startup_tasks(app: FastAPI) -> None:
    """Attach startup/shutdown handlers and scheduled background tasks to the FastAPI app."""
    if getattr(app.state, "_startup_tasks_registered", False):
        return

    app.add_event_handler("startup", _startup_event_factory(app))
    app.add_event_handler("startup", update_search_suggestions_task)
    app.add_event_handler("startup", update_all_post_scores)
    app.add_event_handler("startup", cleanup_old_notifications)
    app.add_event_handler("startup", retry_failed_notifications)
    app.add_event_handler("startup", monitor_cache_size)

    scheduler = _configure_scheduler()
    if scheduler:

        def _shutdown_scheduler() -> None:
            scheduler.shutdown()

        app.add_event_handler("shutdown", _shutdown_scheduler)
        app.state.scheduler = scheduler

    app.state._startup_tasks_registered = True


def _configure_scheduler() -> Optional[BackgroundScheduler]:
    """Configure APScheduler for non-test environments."""
    if settings.environment.lower() == "test":
        # Avoid spinning background threads when tests run synchronously.
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(_clean_old_statistics_job, "cron", hour=0)
    scheduler.add_job(update_all_communities_statistics, "cron", hour=0)
    scheduler.start()
    return scheduler


def _clean_old_statistics_job() -> None:
    """Cron job wrapper to clean analytics statistics safely."""
    db = next(get_db())
    try:
        clean_old_statistics(db)
    finally:
        db.close()


def _startup_event_factory(app: FastAPI):
    """Helper for  startup event factory."""
    async def startup_event() -> None:
        """One-time startup hook for non-test environments (search, AI, Firebase, beat schedule)."""
        if settings.environment.lower() == "test":
            return

        db = SessionLocal()
        create_default_categories(db)
        db.close()
        update_search_vector()

        arabic_words_path = Path(__file__).resolve().parents[2] / "arabic_words.txt"
        if not getattr(app.state, "amenhotep", None):
            app.state.amenhotep_task = asyncio.create_task(_prewarm_amenhotep(app))
        spell.word_frequency.load_dictionary(str(arabic_words_path))
        celery_app.conf.beat_schedule = {
            "check-scheduled-posts": {
                "task": "app.celery_worker.schedule_post_publication",
                "schedule": 60.0,
            },
        }
        model.eval()
        if not initialize_firebase():
            logger.warning(
                "Firebase initialization failed - push notifications will be disabled"
            )

    return startup_event


def update_all_communities_statistics() -> None:
    """Iterate through communities and trigger statistics updates (placeholder behaviour retained)."""
    db = SessionLocal()
    try:
        communities = db.query(Community).all()
        for community in communities:
            router = getattr(community, "router", None)
            if router and hasattr(router, "update_community_statistics"):
                router.update_community_statistics(db, community.id)
    finally:
        db.close()


@_maybe_repeat_every(seconds=60 * 60 * 24)
async def update_search_suggestions_task() -> None:
    """Update search suggestions task."""
    db = next(get_db())
    try:
        update_search_suggestions(db)
    except Exception as exc:  # pragma: no cover - logged for diagnostics
        logger.error("Failed to update search suggestions: %s", exc)
        raise
    finally:
        db.close()


@_maybe_repeat_every(seconds=60 * 60)
async def update_all_post_scores() -> None:
    """Update all post scores."""
    db = SessionLocal()
    try:
        posts = db.query(models.Post).all()
        for post in posts:
            update_post_score(db, post)
    finally:
        db.close()


@_maybe_repeat_every(seconds=86400)
def cleanup_old_notifications() -> None:
    """Prune aged notifications (30d) via NotificationService; tolerates async implementations."""
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        result = notification_service.cleanup_old_notifications(30)
        if inspect.isawaitable(result):
            return _run_async_blocking(result)
        return result
    finally:
        db.close()


@_maybe_repeat_every(seconds=3600)
def retry_failed_notifications() -> None:
    """Retry failed notifications with bounded attempts; logs/raises if all retries fail."""
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
        errors = []
        for notification in notifications:
            try:
                result = notification_service.retry_failed_notification(notification.id)
                if inspect.isawaitable(result):
                    _run_async_blocking(result)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(
                    "Failed to retry notification %s: %s", notification.id, exc
                )
                errors.append(exc)
        if errors and len(errors) == len(notifications):
            # Surface failure when every notification retry failed.
            raise errors[0]
    finally:
        db.close()


@_maybe_repeat_every(seconds=3600)
async def monitor_cache_size() -> None:
    """Log Redis cache size to help track growth and TTL effectiveness."""
    if not cache_manager.enabled or not cache_manager.redis:
        return None
    try:
        size = await cache_manager.redis.dbsize()
        logger.info("Redis cache size: %s keys", size)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to read Redis cache size: %s", exc)


@_maybe_repeat_every(seconds=1800)
def cleanup_expired_reels_task() -> None:
    """Helper for cleanup expired reels task."""
    db = SessionLocal()
    try:
        return ReelService(db).cleanup_expired_reels()
    except Exception as exc:  # pragma: no cover - defensive log
        logger.error("Failed to cleanup expired reels: %s", exc)
        raise
    finally:
        db.close()
