"""Test module for test scheduling tasks session29."""
import asyncio
import types

import pytest

from app.core.scheduling import tasks


def test_run_async_blocking_creates_loop_when_missing(monkeypatch):
    """Test case for test run async blocking creates loop when missing."""
    real_new_loop = asyncio.new_event_loop
    created = {}
    set_loop = {}

    def fake_get_event_loop():
        raise RuntimeError("no loop")

    def fake_new_event_loop():
        created["loop"] = real_new_loop()
        return created["loop"]

    def fake_set_event_loop(loop):
        set_loop["loop"] = loop

    monkeypatch.setattr(asyncio, "get_event_loop", fake_get_event_loop)
    monkeypatch.setattr(asyncio, "new_event_loop", fake_new_event_loop)
    monkeypatch.setattr(asyncio, "set_event_loop", fake_set_event_loop)

    async def sample():
        return "ok"

    assert tasks._run_async_blocking(sample()) == "ok"
    assert created["loop"] is set_loop["loop"]


def test_maybe_repeat_every_skips_sync_in_tests():
    """Test case for test maybe repeat every skips sync in tests."""
    calls = []

    @tasks._maybe_repeat_every(seconds=1)
    def sync_job(x):
        calls.append(x)
        return "ran"

    assert sync_job(123) is None
    assert calls == []


def test_clean_old_statistics_job_closes_session(monkeypatch):
    """Test case for test clean old statistics job closes session."""
    closed = {"value": False}
    called = {"value": False}

    class FakeSession:
        def close(self):
            closed["value"] = True

    def fake_get_db():
        yield FakeSession()

    def fake_clean(session):
        called["value"] = True
        assert session is not None

    monkeypatch.setattr(tasks, "get_db", fake_get_db)
    monkeypatch.setattr(tasks, "clean_old_statistics", fake_clean)

    tasks._clean_old_statistics_job()

    assert called["value"] is True
    assert closed["value"] is True


@pytest.mark.asyncio
async def test_startup_event_factory_bails_in_test_env(monkeypatch):
    """Test case for test startup event factory bails in test env."""
    app = types.SimpleNamespace(state=types.SimpleNamespace())

    def fail_call(*args, **kwargs):
        pytest.fail("startup work should be skipped in test env")

    monkeypatch.setattr(tasks.settings, "environment", "test")
    monkeypatch.setattr(tasks, "create_default_categories", fail_call)
    monkeypatch.setattr(tasks, "update_search_vector", fail_call)
    async def fake_amenhotep(*_):
        fail_call()

    monkeypatch.setattr(tasks, "get_shared_amenhotep", fake_amenhotep)
    monkeypatch.setattr(tasks, "initialize_firebase", lambda: True)

    startup_event = tasks._startup_event_factory(app)
    await startup_event()
    assert not hasattr(app.state, "amenhotep_task")


def test_update_all_communities_statistics_invokes_router(monkeypatch):
    """Test case for test update all communities statistics invokes router."""
    called = {}

    class FakeRouter:
        def update_community_statistics(self, db, community_id):
            called["args"] = (db, community_id)

    class FakeCommunity:
        def __init__(self):
            self.id = 9
            self.router = FakeRouter()

    class FakeQuery:
        def all(self):
            return [FakeCommunity()]

    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, model):
            return FakeQuery()

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    tasks.update_all_communities_statistics()

    assert called["args"][1] == 9
    assert session.closed is True


@pytest.mark.asyncio
async def test_update_search_suggestions_task_runs_and_closes(monkeypatch):
    """Test case for test update search suggestions task runs and closes."""
    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    session = FakeSession()
    called = {"ran": False}

    def fake_get_db():
        yield session

    def fake_update(db):
        called["ran"] = True
        assert db is session

    monkeypatch.setattr(tasks, "get_db", fake_get_db)
    monkeypatch.setattr(tasks, "update_search_suggestions", fake_update)

    await tasks.update_search_suggestions_task.__wrapped__()

    assert called["ran"] is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_update_all_post_scores_updates_each(monkeypatch):
    """Test case for test update all post scores updates each."""
    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, model):
            class Query:
                def all(self_inner):
                    p1 = types.SimpleNamespace(id=1)
                    p2 = types.SimpleNamespace(id=2)
                    return [p1, p2]

            return Query()

        def close(self):
            self.closed = True

    session = FakeSession()
    called = []

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        tasks, "update_post_score", lambda db, post: called.append(post.id)
    )

    await tasks.update_all_post_scores.__wrapped__()

    assert called == [1, 2]
    assert session.closed is True


def test_cleanup_old_notifications_handles_awaitable(monkeypatch):
    """Test case for test cleanup old notifications handles awaitable."""
    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    session = FakeSession()
    blocked = {"called": False}

    async def fake_coro():
        return "async-result"

    original_run_async = tasks._run_async_blocking

    def fake_run_async(awaitable):
        blocked["called"] = True
        return original_run_async(awaitable)

    class FakeService:
        def __init__(self, db):
            self.db = db

        def cleanup_old_notifications(self, days):
            assert days == 30
            return fake_coro()

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "_run_async_blocking", fake_run_async)
    monkeypatch.setattr(tasks, "NotificationService", FakeService)

    result = tasks.cleanup_old_notifications.__wrapped__()

    assert blocked["called"] is True
    assert session.closed is True
    assert result == "async-result"


def test_retry_failed_notifications_raises_when_all_fail(monkeypatch):
    """Test case for test retry failed notifications raises when all fail."""
    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, model):
            class Query:
                def filter(self_inner, *args, **kwargs):
                    return self_inner

                def all(self_inner):
                    class Notification:
                        def __init__(self, nid):
                            self.id = nid

                    return [Notification(1), Notification(2)]

            return Query()

        def close(self):
            self.closed = True

    session = FakeSession()

    class FakeService:
        def __init__(self, db):
            self.db = db

        def retry_failed_notification(self, notification_id):
            raise RuntimeError(f"fail {notification_id}")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "NotificationService", FakeService)

    with pytest.raises(RuntimeError):
        tasks.retry_failed_notifications.__wrapped__()

    assert session.closed is True


def test_configure_scheduler_none_in_test_env(monkeypatch):
    """Test case for test configure scheduler none in test env."""
    monkeypatch.setattr(tasks.settings, "environment", "test")
    assert tasks._configure_scheduler() is None


def test_register_startup_tasks_adds_shutdown_once(monkeypatch):
    """Test case for test register startup tasks adds shutdown once."""
    monkeypatch.setattr(tasks.settings, "environment", "dev")

    class FakeScheduler:
        def __init__(self):
            self.jobs = []
            self.started = 0
            self.shutdown_called = 0

        def add_job(self, job, *_args, **_kwargs):
            self.jobs.append(job)

        def start(self):
            self.started += 1

        def shutdown(self):
            self.shutdown_called += 1

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "BackgroundScheduler", lambda: fake_scheduler)

    class FakeApp:
        def __init__(self):
            self.handlers = []
            self.state = types.SimpleNamespace(_startup_tasks_registered=False)

        def add_event_handler(self, event, fn):
            self.handlers.append((event, fn))

    app = FakeApp()
    tasks.register_startup_tasks(app)

    assert fake_scheduler.started == 1
    # capture shutdown handler
    shutdown_handlers = [fn for event, fn in app.handlers if event == "shutdown"]
    assert len(shutdown_handlers) == 1
    shutdown_handlers[0]()
    assert fake_scheduler.shutdown_called == 1

    # Second registration is a no-op
    pre_count = len(app.handlers)
    tasks.register_startup_tasks(app)
    assert len(app.handlers) == pre_count
    assert app.state._startup_tasks_registered is True
