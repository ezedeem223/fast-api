from unittest.mock import MagicMock

import pytest

from app.celery_worker import celery_app, cleanup_old_notifications
from app.modules.notifications.tasks import send_push_notification_task

# ============== 30) send_push_notification_task ==============


def test_send_push_notification_no_devices_noop(monkeypatch):
    class FakeNotif:
        def __init__(self):
            self.id = 1
            self.user_id = 1
            self.content = "payload"
            self.notification_type = "t"
            self.link = None

    class FakeDevice:
        def __init__(self):
            self.fcm_token = "tok"
            self.is_active = False

    class FakeAttr:
        def __eq__(self, other):
            return True

        def is_(self, other):
            return True

    class FakeLegacy:
        class UserDevice:
            user_id = FakeAttr()
            is_active = FakeAttr()

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def filter(self, *_, **__):
            return self

        def all(self):
            return self._result

    class FakeSession:
        def __init__(self):
            self.notif = FakeNotif()
            self.committed = False

        def get(self, *_, **__):
            return self.notif

        def query(self, *_, **__):
            return FakeQuery([])

        def commit(self):
            self.committed = True

    fake_session = FakeSession()
    monkeypatch.setattr("app.modules.notifications.tasks.legacy_models", FakeLegacy)
    send_push_notification_task(fake_session, 1)
    assert fake_session.committed is True


def test_send_push_notification_sends(monkeypatch):
    class FakeNotif:
        def __init__(self):
            self.id = 1
            self.user_id = 1
            self.content = "payload"
            self.notification_type = "t"
            self.link = None

    class FakeDevice:
        def __init__(self):
            self.fcm_token = "tok"
            self.is_active = True

    class FakeAttr:
        def __eq__(self, other):
            return True

        def is_(self, other):
            return True

    class FakeLegacy:
        class UserDevice:
            user_id = FakeAttr()
            is_active = FakeAttr()

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def filter(self, *_, **__):
            return self

        def all(self):
            return self._result

    class FakeSession:
        def __init__(self):
            self.notif = FakeNotif()
            self.committed = False

        def get(self, *_, **__):
            return self.notif

        def query(self, *_, **__):
            return FakeQuery([FakeDevice()])

        def commit(self):
            self.committed = True

    send_mock = MagicMock()
    monkeypatch.setattr("app.modules.notifications.tasks.messaging.send", send_mock)
    monkeypatch.setattr("app.modules.notifications.tasks.legacy_models", FakeLegacy)
    fake_session = FakeSession()
    send_push_notification_task(fake_session, 1)
    assert send_mock.called
    assert fake_session.committed is True


def test_send_push_notification_logs_on_error(monkeypatch, caplog):
    class FakeNotif:
        def __init__(self):
            self.id = 1
            self.user_id = 1
            self.content = "payload"
            self.notification_type = "t"
            self.link = None

    class FakeDevice:
        def __init__(self):
            self.fcm_token = "tok"
            self.is_active = True

    class FakeAttr:
        def __eq__(self, other):
            return True

        def is_(self, other):
            return True

    class FakeLegacy:
        class UserDevice:
            user_id = FakeAttr()
            is_active = FakeAttr()

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def filter(self, *_, **__):
            return self

        def all(self):
            return self._result

    class FakeSession:
        def __init__(self):
            self.notif = FakeNotif()
            self.committed = False

        def get(self, *_, **__):
            return self.notif

        def query(self, *_, **__):
            return FakeQuery([FakeDevice()])

        def commit(self):
            self.committed = True

    def fail_send(*_, **__):
        raise RuntimeError(
            "send fail"
        )  # simulate push transport error to exercise logging path

    monkeypatch.setattr("app.modules.notifications.tasks.messaging.send", fail_send)
    monkeypatch.setattr("app.modules.notifications.tasks.legacy_models", FakeLegacy)
    fake_session = FakeSession()
    caplog.set_level("ERROR")
    send_push_notification_task(fake_session, 1)
    assert any(
        "Error sending push notification" in rec.message for rec in caplog.records
    )
    assert fake_session.committed is True


# ============== 31) celery eager mode ==============


def test_celery_eager_mode_settings(monkeypatch):
    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=True,
        beat_schedule={},
    )
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.beat_schedule == {}


# ============== 32) celery cleanup_old_notifications ==============


def test_celery_cleanup_old_notifications_closes_db(monkeypatch):
    from app import celery_worker

    close_flag = {"closed": False}

    class FakeSession:
        def query(self, *_, **__):
            return self

        def filter(self, *_, **__):
            return self

        def update(self, *_, **__):
            return 0

        def commit(self):
            pass

        def close(self):
            close_flag["closed"] = True

    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession())
    cleanup_old_notifications()
    assert close_flag["closed"] is True


def test_celery_cleanup_old_notifications_handles_exception(monkeypatch):
    from app import celery_worker

    close_flag = {"closed": False}

    class FakeSession:
        def close(self):
            close_flag["closed"] = True

    def fake_task(db):
        raise RuntimeError("task fail")

    monkeypatch.setattr(celery_worker, "cleanup_old_notifications_task", fake_task)
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession())
    with pytest.raises(RuntimeError):
        cleanup_old_notifications()
    assert close_flag["closed"] is True


def test_celery_cleanup_old_notifications_multiple_calls(monkeypatch):
    from app import celery_worker

    call_count = {"n": 0}

    class FakeSession:
        def close(self):
            pass

    def fake_task(db):
        call_count["n"] += 1

    monkeypatch.setattr(celery_worker, "cleanup_old_notifications_task", fake_task)
    monkeypatch.setattr(celery_worker, "SessionLocal", lambda: FakeSession())
    cleanup_old_notifications()
    cleanup_old_notifications()
    assert call_count["n"] == 2
