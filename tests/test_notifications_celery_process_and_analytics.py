from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import celery_worker
from app.celery_worker import (
    process_scheduled_notifications,
    deliver_notification,
)
from app.modules.notifications import models as notification_models


# ============== 33) celery process_scheduled_notifications ==============


def test_celery_process_scheduled_notifications_enqueues(monkeypatch, session, test_user):
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

    called = {"ids": []}

    def fake_delay(notification_id):
        called["ids"].append(notification_id)

    class FakeSession:
        # Wrap real session so we can monkeypatch SessionLocal without altering commit/query behavior.
        def __init__(self, real):
            self.real = real

        def close(self):
            pass

        def commit(self):
            return self.real.commit()

        def query(self, *args, **kwargs):
            return self.real.query(*args, **kwargs)

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession(session))
    monkeypatch.setattr(celery_worker, "deliver_notification", type("T", (), {"delay": staticmethod(fake_delay)}))
    process_scheduled_notifications()
    assert called["ids"] == [n.id]


def test_celery_process_scheduled_notifications_no_pending(monkeypatch):
    class FakeQuery:
        def filter(self, *_, **__):
            return self

        def all(self):
            return []

    class FakeSession:
        def query(self, *_, **__):
            return FakeQuery()

        def commit(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession())
    process_scheduled_notifications()  # should not raise


def test_celery_process_scheduled_notifications_closes_db(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, *_, **__):
            class Q:
                def filter(self, *_, **__):
                    return self

                def all(self):
                    return []

            return Q()

        def commit(self):
            pass

        def close(self):
            self.closed = True

    fake = FakeSession()
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: fake)
    process_scheduled_notifications()
    assert fake.closed is True


# ============== 34) celery deliver_notification ==============


def test_celery_deliver_notification_missing(monkeypatch):
    class FakeSession:
        def close(self):
            self.closed = True

        def get(self, *_, **__):
            return None

        def query(self, *_, **__):
            return []

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession())
    deliver_notification(123)  # should no-op without error


def test_celery_deliver_notification_calls_email_and_push(monkeypatch, session, test_user):
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="hi",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(n)
    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=False,
    )
    session.add(prefs)
    session.commit()
    session.refresh(n)

    calls = {"email": 0, "push": 0}

    def fake_email(notification):
        calls["email"] += 1

    def fake_push(notif_id):
        calls["push"] += 1

    monkeypatch.setattr(
        celery_worker,
        "send_email_task",
        SimpleNamespace(delay=lambda *_, **__: fake_email(n)),
    )
    monkeypatch.setattr(
        celery_worker,
        "send_push_notification",
        SimpleNamespace(delay=lambda *_, **__: fake_push(n.id)),
    )
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: session)
    deliver_notification(n.id)
    assert calls["email"] == 1
    assert calls["push"] == 1


def test_celery_deliver_notification_handles_exceptions(monkeypatch, session, test_user, caplog):
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="hi",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
    )
    session.add(n)
    session.commit()
    session.refresh(n)

    def bad_email(*_, **__):
        raise RuntimeError("email fail")

    def bad_push(*_, **__):
        raise RuntimeError("push fail")

    prefs = notification_models.NotificationPreferences(
        user_id=test_user["id"],
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=False,
    )
    session.add(prefs)
    session.commit()
    caplog.set_level("ERROR", logger="app.notifications")

    monkeypatch.setattr(
        celery_worker,
        "send_email_task",
        SimpleNamespace(delay=bad_email),
    )
    monkeypatch.setattr(
        celery_worker,
        "send_push_notification",
        SimpleNamespace(delay=bad_push),
    )
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: session)
    deliver_notification(n.id)
    assert any("email fail" in rec.message for rec in caplog.records)
    assert any("push fail" in rec.message for rec in caplog.records)


# ============== 35) update_notification_analytics/calc_user_metrics ==============


def test_calc_user_metrics_creates_and_updates(session, test_user):
    # create analytics
    res = celery_worker.calculate_user_notification_analytics(session, test_user["id"])
    assert isinstance(res, dict)
    # add a notification with read_at missing -> response_time stays 0
    n = notification_models.Notification(
        user_id=test_user["id"],
        content="hi",
        notification_type="t",
        status=notification_models.NotificationStatus.PENDING,
        is_read=True,
        read_at=None,
    )
    session.add(n)
    session.commit()
    res = celery_worker.calculate_user_notification_analytics(session, test_user["id"])
    assert res["response_time"] == 0.0


def test_calc_user_metrics_peak_hours(session, test_user):
    now = datetime.now(timezone.utc)
    for hour in [1, 1, 2, 3, 3, 3]:
        dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        n = notification_models.Notification(
            user_id=test_user["id"],
            content="h",
            notification_type="t",
            status=notification_models.NotificationStatus.PENDING,
            created_at=dt,
        )
        session.add(n)
    session.commit()
    res = celery_worker.calculate_user_notification_analytics(session, test_user["id"])
    assert res["peak_hours"][0] == 3
