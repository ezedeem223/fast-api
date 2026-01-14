"""Covers scheduler startup/beat wiring and environment guards without touching real schedulers or Firebase."""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.scheduling import tasks
from fastapi import FastAPI


def _set_env(monkeypatch, value: str):
    """Helper for  set env."""
    monkeypatch.setenv("APP_ENV", value)
    object.__setattr__(settings, "environment", value)


def test_maybe_repeat_every_skips_in_test_env(monkeypatch):
    """Test case for test maybe repeat every skips in test env."""
    _set_env(monkeypatch, "test")
    called = {"count": 0}

    def fn():
        called["count"] += 1

    wrapper = tasks._maybe_repeat_every(seconds=0)(fn)
    result = wrapper()  # wrapper should be a no-op in test env
    assert result is None
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_maybe_repeat_every_runs_in_prod(monkeypatch):
    """Test case for test maybe repeat every runs in prod."""
    _set_env(monkeypatch, "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    called = {"count": 0}

    def fn():
        called["count"] += 1

    wrapper = tasks._maybe_repeat_every(seconds=0)(fn)
    wrapper.__wrapped__()  # type: ignore[attr-defined]
    assert called["count"] == 1


@pytest.mark.asyncio
async def test_startup_handles_amenhotep(monkeypatch, caplog):
    """Test case for test startup handles amenhotep."""
    _set_env(monkeypatch, "production")
    caplog.clear()
    flags = {"amenhotep": 0, "categories": 0, "search": 0, "eval": 0, "spell": 0}
    fake_session = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        tasks, "create_default_categories", lambda db: flags.__setitem__("categories", 1)
    )
    monkeypatch.setattr(
        tasks, "update_search_vector", lambda: flags.__setitem__("search", 1)
    )
    monkeypatch.setattr(
        tasks, "celery_app", SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    )
    monkeypatch.setattr(
        tasks, "model", SimpleNamespace(eval=lambda: flags.__setitem__("eval", 1))
    )
    monkeypatch.setattr(tasks, "initialize_firebase", lambda: True)
    monkeypatch.setattr(
        tasks,
        "spell",
        SimpleNamespace(
            word_frequency=SimpleNamespace(
                load_dictionary=lambda _: flags.__setitem__("spell", 1)
            )
        ),
    )

    async def fake_amenhotep(*_):
        flags["amenhotep"] += 1
        return None

    monkeypatch.setattr(tasks, "get_shared_amenhotep", fake_amenhotep)
    monkeypatch.setattr(
        tasks, "celery_app", SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    )
    app = FastAPI()
    startup = tasks._startup_event_factory(app)
    await startup()
    await asyncio.sleep(0)
    assert flags["categories"] == 1
    assert flags["search"] == 1
    assert flags["eval"] == 1
    assert flags["spell"] == 1
    assert hasattr(app.state, "amenhotep_task")


@pytest.mark.asyncio
async def test_startup_warns_on_firebase_failure(monkeypatch, caplog):
    """Test case for test startup warns on firebase failure."""
    _set_env(monkeypatch, "production")
    caplog.clear()
    fake_session = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(tasks, "create_default_categories", lambda db: None)
    monkeypatch.setattr(tasks, "update_search_vector", lambda: None)
    async def fake_amenhotep(*_):
        return None

    monkeypatch.setattr(tasks, "get_shared_amenhotep", fake_amenhotep)
    monkeypatch.setattr(
        tasks,
        "spell",
        SimpleNamespace(
            word_frequency=SimpleNamespace(load_dictionary=lambda path: path)
        ),
    )
    monkeypatch.setattr(
        tasks, "celery_app", SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    )
    monkeypatch.setattr(tasks, "model", SimpleNamespace(eval=lambda: None))
    monkeypatch.setattr(tasks, "initialize_firebase", lambda: False)

    startup = tasks._startup_event_factory(FastAPI())
    await startup()
    assert "push notifications will be disabled" in caplog.text


@pytest.mark.asyncio
async def test_startup_loads_spell_dictionary(monkeypatch):
    """Test case for test startup loads spell dictionary."""
    _set_env(monkeypatch, "production")
    loaded = {}
    fake_session = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(tasks, "create_default_categories", lambda db: None)
    monkeypatch.setattr(tasks, "update_search_vector", lambda: None)
    async def fake_amenhotep(*_):
        return None

    monkeypatch.setattr(tasks, "get_shared_amenhotep", fake_amenhotep)
    monkeypatch.setattr(
        tasks, "celery_app", SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    )
    monkeypatch.setattr(tasks, "initialize_firebase", lambda: True)
    monkeypatch.setattr(tasks, "model", SimpleNamespace(eval=lambda: None))

    class FakeWF:
        def load_dictionary(self, path):
            loaded["path"] = path

    monkeypatch.setattr(tasks, "spell", SimpleNamespace(word_frequency=FakeWF()))
    startup = tasks._startup_event_factory(FastAPI())
    await startup()
    assert "arabic_words.txt" in loaded["path"]


def test_configure_scheduler_shutdown_called(monkeypatch):
    """Test case for test configure scheduler shutdown called."""
    _set_env(monkeypatch, "production")
    shutdown_called = {"flag": False}

    class FakeScheduler:
        def __init__(self):
            self.started = True

        def add_job(self, *_, **__):
            return None

        def start(self):
            return None

        def shutdown(self):
            shutdown_called["flag"] = True

    monkeypatch.setattr(tasks, "BackgroundScheduler", FakeScheduler)
    app = FastAPI()
    tasks.register_startup_tasks(app)
    assert hasattr(app.state, "scheduler")
    for handler in app.router.on_shutdown:
        handler()
    assert shutdown_called["flag"] is True


@pytest.mark.asyncio
async def test_update_search_suggestions_task_handles_no_redis(monkeypatch):
    """Test case for test update search suggestions task handles no redis."""
    _set_env(monkeypatch, "production")
    called = {"flag": False}

    class FakeDB:
        def close(self):
            called["closed"] = True

    def fake_get_db():
        yield FakeDB()

    monkeypatch.setattr(tasks, "get_db", fake_get_db)
    monkeypatch.setattr(
        tasks, "update_search_suggestions", lambda db: called.__setitem__("flag", True)
    )

    await tasks.update_search_suggestions_task.__wrapped__()  # type: ignore[attr-defined]
    assert called["flag"] is True
    assert called.get("closed") is True


def test_cleanup_old_notifications_uses_sessionlocal(monkeypatch):
    """Test case for test cleanup old notifications uses sessionlocal."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False, "called": False}

    class FakeService:
        def __init__(self, db):
            self.db = db

        def cleanup_old_notifications(self, days):
            flags["called"] = True

    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            flags["closed"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "NotificationService", FakeService)
    tasks.cleanup_old_notifications.__wrapped__()  # type: ignore[attr-defined]
    assert flags["called"] is True
    assert flags["closed"] is True


def test_retry_failed_notifications_respects_retry_limit(monkeypatch):
    """Test case for test retry failed notifications respects retry limit."""
    _set_env(monkeypatch, "production")
    retried = []
    closed = {"flag": False}

    class FakeNotif:
        def __init__(self, status, retry_count):
            self.status = status
            self.retry_count = retry_count
            self.id = retry_count

    class FakeService:
        def __init__(self, db):
            self.db = db

        def retry_failed_notification(self, nid):
            retried.append(nid)

    class FakeQuery:
        def __init__(self, items):
            self._items = items

        def filter(self, *predicates):
            # Only keep failed with retry_count < 3
            filtered = [
                n
                for n in self._items
                if n.status == tasks.models.NotificationStatus.FAILED
                and n.retry_count < 3
            ]
            return FakeQuery(filtered)

        def all(self):
            return self._items

    class FakeSession:
        def __init__(self):
            self.q = FakeQuery(
                [
                    FakeNotif(
                        status=tasks.models.NotificationStatus.FAILED, retry_count=0
                    ),
                    FakeNotif(
                        status=tasks.models.NotificationStatus.FAILED, retry_count=4
                    ),
                ]
            )

        def query(self, *_, **__):
            return self.q

        def close(self):
            closed["flag"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "NotificationService", FakeService)
    tasks.retry_failed_notifications.__wrapped__()  # type: ignore[attr-defined]
    assert retried == [0]
    assert closed["flag"] is True


def test_cleanup_expired_reels_task_closes(monkeypatch):
    """Test case for test cleanup expired reels task closes."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False, "called": False}

    class FakeReelService:
        def __init__(self, db):
            self.db = db

        def cleanup_expired_reels(self):
            flags["called"] = True
            raise RuntimeError("boom")

    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            flags["closed"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "ReelService", FakeReelService)
    with pytest.raises(RuntimeError):
        tasks.cleanup_expired_reels_task.__wrapped__()  # type: ignore[attr-defined]
    assert flags["called"] is True
    assert flags["closed"] is True


# 40) cleanup_old_notifications / retry_failed_notifications


def test_scheduler_cleanup_old_notifications_closes_on_exception(monkeypatch):
    """Test case for test scheduler cleanup old notifications closes on exception."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False}

    class FakeService:
        def __init__(self, db):
            self.db = db

        def cleanup_old_notifications(self, days):
            raise RuntimeError("fail cleanup")

    class FakeSession:
        def close(self):
            flags["closed"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "NotificationService", FakeService)
    with pytest.raises(RuntimeError):
        tasks.cleanup_old_notifications.__wrapped__()  # type: ignore[attr-defined]
    assert flags["closed"] is True


def test_retry_failed_notifications_closes_on_exception(monkeypatch):
    """Test case for test retry failed notifications closes on exception."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False}

    class FakeNotif:
        def __init__(self, rid):
            self.id = rid
            self.status = tasks.models.NotificationStatus.FAILED
            self.retry_count = 0

    class FakeQuery:
        def filter(self, *_, **__):
            return self

        def all(self):
            return [FakeNotif(1)]

    class FakeSession:
        def query(self, *_, **__):
            return FakeQuery()

        def close(self):
            flags["closed"] = True

    class FakeService:
        def __init__(self, db):
            self.db = db

        def retry_failed_notification(self, *_):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "NotificationService", FakeService)
    with pytest.raises(RuntimeError):
        tasks.retry_failed_notifications.__wrapped__()  # type: ignore[attr-defined]
    assert flags["closed"] is True


# 41) cleanup_expired_reels_task success/error


def test_cleanup_expired_reels_task_calls_and_closes(monkeypatch):
    """Test case for test cleanup expired reels task calls and closes."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False, "called": False}

    class FakeReelService:
        def __init__(self, db):
            self.db = db

        def cleanup_expired_reels(self):
            flags["called"] = True

    class FakeSession:
        def close(self):
            flags["closed"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "ReelService", FakeReelService)
    tasks.cleanup_expired_reels_task.__wrapped__()  # type: ignore[attr-defined]
    assert flags["called"] is True
    assert flags["closed"] is True


# 36) _is_test_env


def test_is_test_env_respects_app_env(monkeypatch):
    """Test case for test is test env respects app env."""
    _set_env(monkeypatch, "production")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert tasks._is_test_env() is True


def test_is_test_env_respects_pytest_flag(monkeypatch):
    """Test case for test is test env respects pytest flag."""
    _set_env(monkeypatch, "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x::y")
    assert tasks._is_test_env() is True


def test_is_test_env_false_when_clean(monkeypatch):
    """Test case for test is test env false when clean."""
    _set_env(monkeypatch, "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert tasks._is_test_env() is False


# 37) _maybe_repeat_every extras


def test_maybe_repeat_every_wait_first_and_max_repetitions(monkeypatch):
    """Test case for test maybe repeat every wait first and max repetitions."""
    _set_env(monkeypatch, "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    captured = {"kwargs": None, "calls": 0}

    def fake_repeat_every(**kwargs):
        captured["kwargs"] = kwargs

        def decorator(fn):
            def scheduled(*args, **kws):
                captured["calls"] += 1
                if captured["calls"] > kwargs.get("max_repetitions", 0):
                    return None
                return fn(*args, **kws)

            return scheduled

        return decorator

    monkeypatch.setattr(tasks, "repeat_every", fake_repeat_every)

    calls = {"ran": 0}

    def fn():
        calls["ran"] += 1
        return "ok"

    wrapper = tasks._maybe_repeat_every(seconds=1, wait_first=True, max_repetitions=2)(
        fn
    )
    assert wrapper() == "ok"
    assert wrapper() == "ok"
    assert wrapper() is None  # exceeded max_repetitions
    assert captured["kwargs"] == {
        "seconds": 1,
        "wait_first": True,
        "max_repetitions": 2,
    }
    assert calls["ran"] == 2


# 38) update_search_suggestions_task


@pytest.mark.asyncio
async def test_update_search_suggestions_task_is_noop_in_test(monkeypatch):
    """Test case for test update search suggestions task is noop in test."""
    _set_env(monkeypatch, "test")
    called = {"flag": False}

    async def wrapper():
        called["flag"] = True

    # ensure update function would run if not skipped
    monkeypatch.setattr(
        tasks, "update_search_suggestions", lambda db: called.__setitem__("flag", True)
    )

    def fake_get_db():
        yield SimpleNamespace(close=lambda: called.__setitem__("closed", True))

    monkeypatch.setattr(tasks, "get_db", fake_get_db)
    assert await tasks.update_search_suggestions_task() is None
    assert called["flag"] is False
    assert called.get("closed") is None


@pytest.mark.asyncio
async def test_update_search_suggestions_task_logs_and_closes_on_error(
    monkeypatch, caplog
):
    """Test case for test update search suggestions task logs and closes on error."""
    _set_env(monkeypatch, "production")
    flags = {}

    class FakeDB:
        def close(self):
            flags["closed"] = True

    def fake_get_db():
        yield FakeDB()

    def boom(_):
        raise RuntimeError("search boom")

    monkeypatch.setattr(tasks, "get_db", fake_get_db)
    monkeypatch.setattr(tasks, "update_search_suggestions", boom)
    caplog.set_level("ERROR")
    with pytest.raises(RuntimeError):
        await tasks.update_search_suggestions_task.__wrapped__()  # type: ignore[attr-defined]
    assert flags.get("closed") is True
    assert "search boom" in caplog.text


# 39) update_all_post_scores


@pytest.mark.asyncio
async def test_update_all_post_scores_empty_db(monkeypatch):
    """Test case for test update all post scores empty db."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False}

    class FakeQuery:
        def all(self):
            return []

    class FakeSession:
        def query(self, *_, **__):
            return FakeQuery()

        def close(self):
            flags["closed"] = True

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        tasks,
        "update_post_score",
        lambda db, post: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    await tasks.update_all_post_scores.__wrapped__()  # type: ignore[attr-defined]
    assert flags["closed"] is True


@pytest.mark.asyncio
async def test_update_all_post_scores_updates_posts(monkeypatch):
    """Test case for test update all post scores updates posts."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False, "called": []}

    class FakePost:
        def __init__(self, pid):
            self.id = pid

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    class FakeSession:
        def __init__(self):
            self.q = FakeQuery([FakePost(1), FakePost(2)])

        def query(self, *_, **__):
            return self.q

        def close(self):
            flags["closed"] = True

    def record(db, post):
        flags["called"].append(post.id)

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "update_post_score", record)
    await tasks.update_all_post_scores.__wrapped__()  # type: ignore[attr-defined]
    assert flags["called"] == [1, 2]
    assert flags["closed"] is True


@pytest.mark.asyncio
async def test_update_all_post_scores_closes_on_exception(monkeypatch):
    """Test case for test update all post scores closes on exception."""
    _set_env(monkeypatch, "production")
    flags = {"closed": False}

    class FakeQuery:
        def all(self):
            return [SimpleNamespace(id=1)]

    class FakeSession:
        def query(self, *_, **__):
            return FakeQuery()

        def close(self):
            flags["closed"] = True

    def boom(db, post):
        raise RuntimeError("score fail")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "update_post_score", boom)
    with pytest.raises(RuntimeError):
        await tasks.update_all_post_scores.__wrapped__()  # type: ignore[attr-defined]
    assert flags["closed"] is True
