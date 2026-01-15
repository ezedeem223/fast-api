"""Additional coverage for celery worker branches."""
from __future__ import annotations

import types
from datetime import datetime, timedelta
from pathlib import Path

from app import celery_worker
from app import models


def test_update_notification_analytics_creates_records(monkeypatch):
    """Ensure analytics task updates per-user stats with a stubbed session."""
    class FakeUser:
        def __init__(self, user_id):
            self.id = user_id

    class FakeAnalytics:
        user_id = "user_id"

        def __init__(self, user_id=None):
            self.user_id = user_id
            self.engagement_rate = None
            self.response_time = None
            self.peak_hours = None
            self.updated_at = None

    class FakeQuery:
        def __init__(self, model, db):
            self.model = model
            self.db = db

        def all(self):
            return self.db.users

        def filter(self, *_):
            return self

        def first(self):
            return self.db.analytics_by_user.get(self.db.current_user_id)

    class FakeDB:
        def __init__(self):
            self.users = [FakeUser(1)]
            self.analytics_by_user = {}
            self.current_user_id = None
            self.committed = False
            self.closed = False

        def query(self, model):
            if model is FakeUser:
                return FakeQuery(model, self)
            return FakeQuery(model, self)

        def add(self, obj):
            if isinstance(obj, FakeAnalytics):
                self.analytics_by_user[obj.user_id] = obj

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    db = FakeDB()

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(celery_worker, "calculate_user_notification_analytics", lambda *_: {
        "engagement_rate": 0.5,
        "response_time": 12.0,
        "peak_hours": [1, 2],
    })
    monkeypatch.setattr(celery_worker, "legacy_models", types.SimpleNamespace(User=FakeUser))
    monkeypatch.setattr(celery_worker.notification_models, "NotificationAnalytics", FakeAnalytics)

    celery_worker.update_notification_analytics()

    assert db.analytics_by_user[1].engagement_rate == 0.5
    assert db.committed is True
    assert db.closed is True


def test_clean_expired_blocks_sends_notification(monkeypatch, session):
    """Cover expired block cleanup path with email send."""
    blocker = models.User(email="blocker@example.com", hashed_password="x")
    blocked = models.User(email="blocked@example.com", hashed_password="x")
    session.add_all([blocker, blocked])
    session.commit()
    session.refresh(blocker)
    session.refresh(blocked)
    blocker.username = "blocker"

    expired_block = models.Block(
        blocker_id=blocker.id,
        blocked_id=blocked.id,
        ends_at=datetime.now() - timedelta(days=1),
    )
    session.add(expired_block)
    session.commit()

    sent = {"count": 0}

    def fake_delay(*_, **__):
        sent["count"] += 1

    monkeypatch.setattr(celery_worker.send_email_task, "delay", fake_delay)
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: session)
    celery_worker.clean_expired_blocks()
    assert sent["count"] == 1


def test_some_other_task_noop():
    """Exercise placeholder task."""
    result = celery_worker.some_other_task({"x": 1})
    assert result is None


def test_celery_worker_wrapped_assignment(monkeypatch):
    """Execute module branch that sets __wrapped__ when not in test env."""
    source = Path("app/celery_worker.py")
    module_globals = {
        "__name__": "celery_worker_wrapped_test",
        "__file__": str(source),
        "__package__": "app",
    }
    def _make_dummy():
        def _dummy(*_, **__):
            return None

        return _dummy

    # Prepopulate dummy tasks so __wrapped__ assignment runs.
    dummy_tasks = {}
    for name in [
        "cleanup_old_notifications",
        "process_scheduled_notifications",
        "deliver_notification",
        "send_push_notification",
        "update_notification_analytics",
        "check_old_posts_content",
        "unblock_user",
        "clean_expired_blocks",
        "some_other_task",
        "calculate_ban_effectiveness",
        "remove_expired_bans",
        "reset_report_counters",
        "schedule_post_publication",
    ]:
        dummy = _make_dummy()
        dummy_tasks[name] = dummy
        module_globals[name] = dummy

    monkeypatch.setattr(celery_worker.settings, "environment", "production", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    exec(compile(source.read_text(), module_globals["__file__"], "exec"), module_globals)
    assert dummy_tasks["cleanup_old_notifications"].__wrapped__ is dummy_tasks["cleanup_old_notifications"]
