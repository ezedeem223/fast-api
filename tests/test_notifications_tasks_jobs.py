from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.modules.notifications import models as notification_models
from app.modules.notifications.tasks import (
    cleanup_old_notifications_task,
    deliver_notification_task,
    process_scheduled_notifications_task,
)

# ============== 27) cleanup_old_notifications_task ==============


def test_cleanup_old_notifications_archives_read(session, test_user):
    old_date = (datetime.now(timezone.utc) - timedelta(days=31)).replace(tzinfo=None)
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="old read",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        is_read=True,
        is_archived=False,
        created_at=old_date,
    )
    session.add(n)
    session.commit()
    session.refresh(n)

    cleanup_old_notifications_task(session)
    session.refresh(n)
    assert n.is_archived is True


def test_cleanup_old_notifications_deletes_archived(session, test_user):
    very_old = (datetime.now(timezone.utc) - timedelta(days=91)).replace(tzinfo=None)
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="old archived",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        is_read=True,
        is_archived=True,
        is_deleted=False,
        created_at=very_old,
    )
    session.add(n)
    session.commit()
    session.refresh(n)

    cleanup_old_notifications_task(session)
    session.refresh(n)
    assert n.is_deleted is True


def test_cleanup_old_notifications_no_data_noop(session):
    # Should not raise when there is nothing to process
    cleanup_old_notifications_task(session)


def test_cleanup_old_notifications_commits(monkeypatch, session):
    called = {"commit": 0}

    def wrapped_commit():
        called["commit"] += 1
        return original_commit()

    original_commit = session.commit
    monkeypatch.setattr(session, "commit", wrapped_commit)

    cleanup_old_notifications_task(session)
    assert called["commit"] == 1


# ============== 28) process_scheduled_notifications_task ==============


def test_process_scheduled_notifications_enqueues_and_sets_delivered(
    session, test_user
):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="due",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        scheduled_for=due,
    )
    session.add(n)
    session.commit()
    session.refresh(n)

    calls = []

    def enqueue(notification_id):
        calls.append(notification_id)

    process_scheduled_notifications_task(session, enqueue)
    session.refresh(n)
    assert calls == [n.id]
    assert n.status == notification_models.NotificationStatus.DELIVERED


def test_process_scheduled_notifications_non_due_noop(session, test_user):
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="future",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        scheduled_for=future,
    )
    session.add(n)
    session.commit()

    calls = []

    process_scheduled_notifications_task(session, lambda *_: calls.append("called"))
    session.refresh(n)
    assert calls == []
    assert n.status == notification_models.NotificationStatus.PENDING


def test_process_scheduled_notifications_enqueue_exception_logged(
    monkeypatch, caplog, session, test_user
):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="due",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        scheduled_for=due,
    )
    session.add(n)
    session.commit()

    def bad_enqueue(_):
        raise RuntimeError("queue fail")

    caplog.set_level("ERROR")
    process_scheduled_notifications_task(session, bad_enqueue)
    assert any("queue fail" in rec.message for rec in caplog.records)
    session.refresh(n)
    # status not updated due to enqueue failure
    assert n.status != notification_models.NotificationStatus.DELIVERED


# ============== 29) deliver_notification_task ==============


def _make_prefs(session, user_id, email=True, push=False):
    prefs = notification_models.NotificationPreferences(
        user_id=user_id,
        email_notifications=email,
        push_notifications=push,
        in_app_notifications=False,
    )
    session.add(prefs)
    session.commit()
    return prefs


def test_deliver_notification_task_missing_notification(session):
    email = MagicMock()
    push = MagicMock()
    deliver_notification_task(session, 9999, email, push)
    email.assert_not_called()
    push.assert_not_called()


def test_deliver_notification_task_missing_prefs(session, test_user):
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="msg",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(n)
    session.commit()
    email = MagicMock()
    push = MagicMock()

    deliver_notification_task(session, n.id, email, push)
    email.assert_not_called()
    push.assert_not_called()


def test_deliver_notification_task_email_sender_raises_logged(
    monkeypatch, caplog, session, test_user
):
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="email",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(n)
    _make_prefs(session, test_user["id"], email=True, push=False)
    session.commit()
    caplog.set_level("ERROR")

    def bad_email(_):
        raise RuntimeError("email fail")

    push = MagicMock()
    deliver_notification_task(session, n.id, bad_email, push)
    assert any("email fail" in rec.message for rec in caplog.records)
    push.assert_not_called()


def test_deliver_notification_task_push_sender_raises_logged(
    monkeypatch, caplog, session, test_user
):
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="push",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(n)
    _make_prefs(session, test_user["id"], email=False, push=True)
    session.commit()
    caplog.set_level("ERROR")

    email = MagicMock()

    def bad_push(_):
        raise RuntimeError("push fail")

    deliver_notification_task(session, n.id, email, bad_push)
    assert any("push fail" in rec.message for rec in caplog.records)
