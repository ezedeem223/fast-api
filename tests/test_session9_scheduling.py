import pytest

from app.core.scheduling import tasks
import app.celery_worker as celery_worker
from app import models


def _make_post(session, owner=None, published=False):
    if owner is None:
        owner = models.User(email="p@example.com", hashed_password="x", is_verified=True)
        session.add(owner)
        session.commit()
        session.refresh(owner)
    post = models.Post(owner_id=owner.id, title="t", content="c", is_safe_content=True, is_published=published)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post, owner


@pytest.mark.asyncio
async def test_configure_scheduler_and_repeat_tasks_skip_in_test(monkeypatch):
    monkeypatch.setattr(tasks.settings, "environment", "test", raising=False)
    assert tasks._configure_scheduler() is None
    assert await tasks.update_search_suggestions_task() is None
    assert await tasks.update_all_post_scores() is None


@pytest.mark.asyncio
async def test_cleanup_old_notifications_and_retry(monkeypatch, session):
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None, raising=False)
    called_cleanup = {"count": 0}
    called_retry = {"ids": []}

    class DummyService:
        def __init__(self, _db):
            pass

        def cleanup_old_notifications(self, days):
            called_cleanup["count"] += 1

        def retry_failed_notification(self, notif_id):
            called_retry["ids"].append(notif_id)

    monkeypatch.setattr(tasks, "NotificationService", DummyService)

    ok = models.Notification(user_id=1, content="c", notification_type="t")
    fail = models.Notification(
        user_id=1,
        content="c",
        notification_type="t",
        status=models.NotificationStatus.FAILED,
        retry_count=0,
    )
    too_many = models.Notification(
        user_id=1,
        content="c",
        notification_type="t",
        status=models.NotificationStatus.FAILED,
        retry_count=5,
    )
    session.add_all([ok, fail, too_many])
    session.commit()

    tasks.cleanup_old_notifications.__wrapped__()  # call underlying to avoid repeat loop
    assert called_cleanup["count"] == 1

    tasks.retry_failed_notifications.__wrapped__()
    assert called_retry["ids"] == [fail.id]


def test_celery_schedule_post_publication(monkeypatch, session):
    post, owner = _make_post(session, published=False)

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None, raising=False)
    called = {"count": 0}

    def fake_send_notifications_and_share(_req, post_obj, user_obj):
        called["count"] += 1
        assert post_obj.id == post.id
        assert user_obj.id == owner.id

    import app.routers.post as post_router
    monkeypatch.setattr(post_router, "send_notifications_and_share", fake_send_notifications_and_share, raising=False)

    celery_worker.schedule_post_publication(post.id)
    session.refresh(post)
    assert post.is_published is True
    assert called["count"] == 1

    # missing post should no-op
    celery_worker.schedule_post_publication(999999)


def test_celery_cleanup_and_process_wrappers(monkeypatch, session):
    flags = {"cleanup": False, "process": False}
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None, raising=False)
    monkeypatch.setattr(celery_worker, "cleanup_old_notifications_task", lambda db: flags.__setitem__("cleanup", True))

    def fake_process(db, enqueue_delivery):
        flags["process"] = True
    monkeypatch.setattr(celery_worker, "process_scheduled_notifications_task", fake_process)

    # stub deliver_notification.delay used by process_scheduled_notifications
    class DummyDeliver:
        @staticmethod
        def delay(notification_id):
            return notification_id
    monkeypatch.setattr(celery_worker, "deliver_notification", DummyDeliver)

    celery_worker.cleanup_old_notifications()
    celery_worker.process_scheduled_notifications()
    assert flags["cleanup"] is True
    assert flags["process"] is True
