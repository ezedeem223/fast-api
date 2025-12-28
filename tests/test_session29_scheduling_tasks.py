import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import models
from app.core.scheduling import tasks
from app.modules.notifications import models as notif_models
from app.modules.community import models as community_models


def test_repeat_every_guard_skips_in_test_env(monkeypatch):
    called = {"hit": False}

    def boom(_db):
        called["hit"] = True
        raise RuntimeError("should not execute in test env")

    monkeypatch.setattr(tasks, "update_search_suggestions", boom)
    asyncio.run(tasks.update_search_suggestions_task())
    assert called["hit"] is False


def test_register_startup_tasks_idempotent(monkeypatch):
    app = FastAPI()
    original_env = tasks.settings.environment
    monkeypatch.setattr(tasks.settings, "environment", "production")
    try:
        tasks.register_startup_tasks(app)
        first_handlers = list(app.router.on_startup)
        scheduler_first = getattr(app.state, "scheduler", None)

        tasks.register_startup_tasks(app)
        assert len(app.router.on_startup) == len(first_handlers)
        assert getattr(app.state, "scheduler", None) is scheduler_first
    finally:
        if getattr(app.state, "scheduler", None):
            app.state.scheduler.shutdown()
        monkeypatch.setattr(tasks.settings, "environment", original_env)


def test_notification_cleanup_and_retry_tasks(session, monkeypatch):
    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=session.get_bind()),
    )
    user = models.User(email="sched29@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    old_archived = notif_models.Notification(
        user_id=user.id,
        content="old archived",
        is_archived=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
        status=notif_models.NotificationStatus.FAILED,
    )
    recent_archived = notif_models.Notification(
        user_id=user.id,
        content="recent archived",
        is_archived=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        status=notif_models.NotificationStatus.FAILED,
    )
    retry_ok = notif_models.Notification(
        user_id=user.id,
        content="retry me",
        status=notif_models.NotificationStatus.FAILED,
        retry_count=0,
    )
    retry_fail = notif_models.Notification(
        user_id=user.id,
        content="retry fails",
        status=notif_models.NotificationStatus.FAILED,
        retry_count=1,
    )
    session.add_all([old_archived, recent_archived, retry_ok, retry_fail])
    session.commit()
    deleted_id = old_archived.id

    removed = tasks.cleanup_old_notifications.__wrapped__()  # type: ignore[attr-defined]
    assert removed == 1

    async def fake_retry(self, notification_id: int):
        notif = self.db.get(notif_models.Notification, notification_id)
        if notif.id == retry_fail.id:
            raise RuntimeError("boom")
        notif.status = notif_models.NotificationStatus.DELIVERED
        notif.retry_count += 1
        self.db.commit()
        return True

    monkeypatch.setattr(tasks.NotificationService, "retry_failed_notification", fake_retry)
    tasks.retry_failed_notifications.__wrapped__()  # type: ignore[attr-defined]

    session.refresh(retry_ok)
    session.refresh(retry_fail)
    assert retry_ok.status == notif_models.NotificationStatus.DELIVERED
    assert retry_ok.retry_count == 1
    assert retry_fail.status == notif_models.NotificationStatus.FAILED
    assert retry_fail.retry_count == 1
    assert session.query(notif_models.Notification).filter_by(id=deleted_id).count() == 0
    assert session.query(notif_models.Notification).filter_by(id=recent_archived.id).count() == 1


def test_cleanup_expired_reels_task(session, monkeypatch):
    SessionLocalOverride = sessionmaker(autocommit=False, autoflush=False, bind=session.get_bind())
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocalOverride)
    user = models.User(email="reels29@example.com", hashed_password="x", is_verified=True)
    community = community_models.Community(name="C29", description="d", owner_id=None)
    session.add_all([user, community])
    session.commit()
    session.refresh(user)
    session.refresh(community)

    expired = community_models.Reel(
        title="old reel",
        video_url="http://example.com/r1",
        description="",
        owner_id=user.id,
        community_id=community.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        is_active=True,
    )
    active = community_models.Reel(
        title="new reel",
        video_url="http://example.com/r2",
        description="",
        owner_id=user.id,
        community_id=community.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        is_active=True,
    )
    session.add_all([expired, active])
    session.commit()
    session.refresh(expired)
    session.refresh(active)

    cleaned = tasks.cleanup_expired_reels_task.__wrapped__()  # type: ignore[attr-defined]
    assert cleaned == 1

    session.refresh(expired)
    session.refresh(active)
    assert expired.is_active is False
    assert active.is_active is True
    archived = session.query(community_models.ArchivedReel).filter_by(reel_id=expired.id).first()
    assert archived is not None

    cleaned_again = tasks.cleanup_expired_reels_task.__wrapped__()  # type: ignore[attr-defined]
    assert cleaned_again == 0
