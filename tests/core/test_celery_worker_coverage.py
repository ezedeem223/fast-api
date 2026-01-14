"""Targeted coverage tests for celery worker tasks."""

from datetime import datetime, timedelta, timezone
from app import models
from app.modules.notifications import models as notification_models
from app import celery_worker as cw
from tests.conftest import TestingSessionLocal


def test_celery_wrapped_task_stubs(monkeypatch):
    called = {}

    class DummyDB:
        def close(self):
            called["closed"] = True

    dummy_db = DummyDB()
    monkeypatch.setattr(cw, "SessionLocal", lambda: dummy_db)

    monkeypatch.setattr(cw, "cleanup_old_notifications_task", lambda db: called.setdefault("cleanup", db))
    monkeypatch.setattr(
        cw,
        "process_scheduled_notifications_task",
        lambda db, enqueue_delivery: called.setdefault("process", db),
    )
    monkeypatch.setattr(
        cw,
        "notification_delivery_handler",
        lambda db, notification_id, email_sender, push_sender: called.setdefault("deliver", notification_id),
    )
    monkeypatch.setattr(
        cw,
        "notification_push_handler",
        lambda db, notification_id: called.setdefault("push", notification_id),
    )

    cw.cleanup_old_notifications()
    cw.process_scheduled_notifications()
    cw.deliver_notification(123)
    cw.send_push_notification(456)

    assert called["cleanup"] is dummy_db
    assert called["process"] is dummy_db
    assert called["deliver"] == 123
    assert called["push"] == 456


def test_send_email_task_success_and_failure(monkeypatch):
    sent = {}

    def _ok_send(message):
        sent["ok"] = message

    monkeypatch.setattr(cw.fm, "send_message", _ok_send)
    cw.send_email_task(["a@example.com"], "subj", "body")
    assert "ok" in sent

    def _boom_send(message):
        raise RuntimeError("fail")

    monkeypatch.setattr(cw.fm, "send_message", _boom_send)
    cw.send_email_task(["b@example.com"], "subj", "body")


def test_calculate_user_notification_analytics(session):
    user = models.User(email="n1@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    empty = cw.calculate_user_notification_analytics(session, user.id)
    assert empty["engagement_rate"] == 0.0

    now = datetime.now(timezone.utc)
    n1 = notification_models.Notification(
        user_id=user.id,
        content="a",
        notification_type="system",
        created_at=now - timedelta(hours=1),
        is_read=True,
        read_at=now,
    )
    n2 = notification_models.Notification(
        user_id=user.id,
        content="b",
        notification_type="system",
        created_at=now - timedelta(hours=2),
        is_read=False,
    )
    session.add_all([n1, n2])
    session.commit()

    metrics = cw.calculate_user_notification_analytics(session, user.id)
    assert metrics["engagement_rate"] > 0
    assert metrics["peak_hours"]


def test_check_old_posts_content(monkeypatch, session):
    user = models.User(email="post@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    post = models.Post(owner_id=user.id, title="t", content="c", is_flagged=False)
    session.add(post)
    session.commit()

    monkeypatch.setattr(cw, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(cw, "is_content_offensive", lambda text: (True, 0.9))

    cw.check_old_posts_content()
    session.refresh(post)
    assert post.is_flagged is True


def test_unblock_and_clean_blocks(monkeypatch, session):
    user1 = models.User(email="b1@example.com", hashed_password="x", is_verified=True)
    user1.username = "blocker"
    user2 = models.User(email="b2@example.com", hashed_password="x", is_verified=True)
    session.add_all([user1, user2])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)

    block = models.Block(
        blocker_id=user1.id,
        blocked_id=user2.id,
        ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    session.add(block)
    session.commit()

    calls = []
    monkeypatch.setattr(cw, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        cw.legacy_models.User,
        "username",
        property(lambda self: self.email),
        raising=False,
    )
    monkeypatch.setattr(cw.send_email_task, "delay", lambda *args, **kwargs: calls.append(args))

    cw.unblock_user(user1.id, user2.id)
    cw.clean_expired_blocks()
    assert calls


def test_ban_effectiveness_and_cleanup(monkeypatch, session):
    user = models.User(email="ban@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    post = models.Post(owner_id=user.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)
    comment = models.Comment(owner_id=user.id, post_id=post.id, content="c")
    session.add(comment)
    session.commit()

    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    stats = models.BanStatistics(date=yesterday, total_bans=1, ip_bans=0, word_bans=0, user_bans=1)
    session.add(stats)
    session.add(
        models.Report(
            report_reason="spam",
            reporter_id=user.id,
            reported_user_id=user.id,
            created_at=datetime.now(timezone.utc),
            is_valid=True,
        )
    )
    session.commit()

    monkeypatch.setattr(cw, "SessionLocal", TestingSessionLocal)
    cw.calculate_ban_effectiveness()
    session.refresh(stats)
    assert stats.effectiveness_score is not None

    user.current_ban_end = datetime.now(timezone.utc) - timedelta(days=1)
    user.total_reports = 5
    user.valid_reports = 3
    session.commit()

    cw.remove_expired_bans()
    cw.reset_report_counters()
    session.refresh(user)
    assert user.current_ban_end is None
    assert user.total_reports == 0
    assert user.valid_reports == 0


def test_schedule_post_publication(monkeypatch, session):
    user = models.User(email="sched@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    post = models.Post(owner_id=user.id, title="t", content="c", is_published=False)
    session.add(post)
    session.commit()
    session.refresh(post)

    calls = []
    monkeypatch.setattr(cw, "SessionLocal", TestingSessionLocal)
    import app.routers.post as post_router

    monkeypatch.setattr(
        post_router,
        "send_notifications_and_share",
        lambda *args, **kwargs: calls.append(True),
        raising=False,
    )

    cw.schedule_post_publication(post.id)
    session.refresh(post)
    assert post.is_published is True
    assert calls
