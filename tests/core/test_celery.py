"""Test module for test celery session6."""
import pytest

import app.celery_worker as worker


def test_celery_eager_mode_in_test_env(monkeypatch):
    """Test case for test celery eager mode in test env."""
    monkeypatch.setattr(worker.settings, "environment", "test")
    monkeypatch.setenv("APP_ENV", "test")
    assert worker._is_test_env() is True
    # Force in-memory config for isolation and verify eager mode.
    worker.celery_app.conf.broker_url = "memory://"
    worker.celery_app.conf.result_backend = "cache+memory://"
    worker.celery_app.conf.task_always_eager = True
    assert worker.celery_app.conf.task_always_eager is True


def test_cleanup_old_notifications_closes_session(monkeypatch):
    """Test case for test cleanup old notifications closes session."""
    calls = []

    class DummySession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(worker, "SessionLocal", lambda: dummy)

    def fake_task(db):
        calls.append(db)

    monkeypatch.setattr(worker, "cleanup_old_notifications_task", fake_task)

    worker.cleanup_old_notifications()
    assert calls == [dummy]
    assert dummy.closed is True


def test_worker_cleanup_old_notifications_closes_on_exception(monkeypatch):
    """Test case for test worker cleanup old notifications closes on exception."""
    class DummySession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(worker, "SessionLocal", lambda: dummy)

    def boom(db):
        raise RuntimeError("fail")

    monkeypatch.setattr(worker, "cleanup_old_notifications_task", boom)

    with pytest.raises(RuntimeError):
        worker.cleanup_old_notifications()
    assert dummy.closed is True


def test_process_scheduled_notifications_enqueues_and_closes(monkeypatch):
    """Test case for test process scheduled notifications enqueues and closes."""
    deliveries = []
    task_calls = []

    class DummySession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(worker, "SessionLocal", lambda: dummy)

    class DummyDelivery:
        @staticmethod
        def delay(notification_id):
            deliveries.append(notification_id)

    monkeypatch.setattr(worker, "deliver_notification", DummyDelivery)

    def fake_process(db, enqueue_delivery):
        task_calls.append(db)
        enqueue_delivery(123)

    monkeypatch.setattr(worker, "process_scheduled_notifications_task", fake_process)

    worker.process_scheduled_notifications()
    assert deliveries == [123]
    assert task_calls == [dummy]
    assert dummy.closed is True
