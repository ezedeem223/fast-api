"""Centralised scheduling and startup task registration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi_utils.tasks import repeat_every

from app import models
from app.ai_chat.amenhotep import AmenhotepAI
from app.analytics import clean_old_statistics, model
from app.celery_worker import celery_app
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.firebase_config import initialize_firebase
from app.modules.community import Community
from app.modules.utils.analytics import create_default_categories, update_post_score
from app.modules.utils.search import spell, update_search_vector
from app.notifications import NotificationService
from app.modules.search.service import update_search_suggestions
from app.services.reels import ReelService


logger = logging.getLogger(__name__)


def register_startup_tasks(app: FastAPI) -> None:
    """
    Attach startup/shutdown handlers and scheduled background tasks to the FastAPI app.
    """
    app.add_event_handler("startup", _startup_event_factory(app))
    app.add_event_handler("startup", update_search_suggestions_task)
    app.add_event_handler("startup", update_all_post_scores)
    app.add_event_handler("startup", cleanup_old_notifications)
    app.add_event_handler("startup", retry_failed_notifications)

    scheduler = _configure_scheduler()
    if scheduler:
        def _shutdown_scheduler() -> None:
            scheduler.shutdown()

        app.add_event_handler("shutdown", _shutdown_scheduler)
        app.state.scheduler = scheduler


def _configure_scheduler() -> Optional[BackgroundScheduler]:
    if settings.environment.lower() == "test":
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(_clean_old_statistics_job, "cron", hour=0)
    scheduler.add_job(update_all_communities_statistics, "cron", hour=0)
    scheduler.start()
    return scheduler


def _clean_old_statistics_job() -> None:
    db = next(get_db())
    try:
        clean_old_statistics(db)
    finally:
        db.close()


def _startup_event_factory(app: FastAPI):
    async def startup_event() -> None:
        if settings.environment.lower() == "test":
            return

        db = SessionLocal()
        create_default_categories(db)
        db.close()
        update_search_vector()

        arabic_words_path = Path(__file__).resolve().parents[2] / "arabic_words.txt"
        app.state.amenhotep = AmenhotepAI()
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
    """
    Iterate through communities and trigger statistics updates (placeholder behaviour retained).
    """
    db = SessionLocal()
    try:
        communities = db.query(Community).all()
        for community in communities:
            router = getattr(community, "router", None)
            if router and hasattr(router, "update_community_statistics"):
                router.update_community_statistics(db, community.id)
    finally:
        db.close()


@repeat_every(seconds=60 * 60 * 24)
def update_search_suggestions_task() -> None:
    if settings.environment.lower() == "test":
        return
    db = next(get_db())
    try:
        update_search_suggestions(db)
    finally:
        db.close()


@repeat_every(seconds=60 * 60)
def update_all_post_scores() -> None:
    if settings.environment.lower() == "test":
        return
    db = SessionLocal()
    try:
        posts = db.query(models.Post).all()
        for post in posts:
            update_post_score(db, post)
    finally:
        db.close()


@repeat_every(seconds=86400)
def cleanup_old_notifications() -> None:
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        notification_service.cleanup_old_notifications(30)
    finally:
        db.close()


@repeat_every(seconds=3600)
def retry_failed_notifications() -> None:
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


@repeat_every(seconds=1800)
def cleanup_expired_reels_task() -> None:
    if settings.environment.lower() == "test":
        return
    db = SessionLocal()
    try:
        ReelService(db).cleanup_expired_reels()
    finally:
        db.close()
