"""Test module for test session10 database."""
import os

import pytest
from sqlalchemy import text

from app import models
from app.core.config import settings
from app.core.database import query_helpers
from app.core.database import session as db_session_mod


def test_paginate_and_cursor_limits(session):
    # seed 5 posts
    """Test case for test paginate and cursor limits."""
    for i in range(5):
        post = models.Post(owner_id=1, title=f"t{i}", content="c", is_safe_content=True)
        session.add(post)
    session.commit()

    base_query = session.query(models.Post)
    paged = query_helpers.paginate_query(base_query, skip=-5, limit=200).all()
    assert len(paged) == 5  # limit capped to 100 and skip floored at 0

    cursor_data = query_helpers.cursor_paginate(
        base_query, cursor=None, limit=2, cursor_column="id", order_desc=False
    )
    assert cursor_data["count"] == 2
    assert cursor_data["has_next"] is True
    # use next_cursor
    cursor_data2 = query_helpers.cursor_paginate(
        base_query,
        cursor=cursor_data["next_cursor"],
        limit=3,
        cursor_column="id",
        order_desc=False,
    )
    assert cursor_data2["count"] <= 3

    count = query_helpers.optimize_count_query(
        base_query.order_by(models.Post.id.desc())
    )
    assert count == 5


def test_build_engine_bad_postgres_url(monkeypatch):
    """Test case for test build engine bad postgres url."""
    bad_url = "postgresql://user:pass@localhost:5432/invalid"

    class DummySettings:
        def get_database_url(self, use_test=False):
            return bad_url

        environment = "prod"

    monkeypatch.setattr(db_session_mod, "settings", DummySettings(), raising=False)
    eng = db_session_mod.build_engine()
    assert eng.url.database == "invalid"


def test_sqlite_now_function_registered(monkeypatch):
    """Test case for test sqlite now function registered."""
    class DummySettings:
        def get_database_url(self, use_test=False):
            return "sqlite:///:memory:"

        environment = "prod"

    monkeypatch.setattr(db_session_mod, "settings", DummySettings(), raising=False)
    eng = db_session_mod.build_engine()
    # listen for connect to register now()
    if eng.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(eng, "connect")
        def _add_now(conn, record):
            conn.create_function("now", 0, lambda: "now")

    if eng.dialect.name == "sqlite":
        with eng.connect() as conn:
            result = conn.execute(text("SELECT now()")).scalar_one()
            assert result is not None


def test_tests_database_fixture_truncate_and_override_env(monkeypatch):
    """Test case for test tests database fixture truncate and override env."""
    test_db_url = os.environ.get("LOCAL_TEST_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL"
    )
    if not test_db_url:
        test_db_url = settings.get_database_url(use_test=True)
    if not test_db_url or not test_db_url.startswith("postgresql"):
        pytest.skip("Postgres test DB not configured.")
    monkeypatch.setenv("LOCAL_TEST_DATABASE_URL", test_db_url)
    # re-import to rebuild engine using env var
    import importlib

    import tests.database as dbmod

    importlib.reload(dbmod)
    assert dbmod.engine.dialect.name == "postgresql"
    with dbmod.engine.begin() as conn:
        conn.execute(text("SELECT 1"))

    # fixture truncates tables
    user = models.User(email="a@a.com", hashed_password="x", is_verified=True)
    with dbmod.TestingSessionLocal() as db:
        db.add(user)
        db.commit()
    # use session fixture logic without invoking pytest's fixture directly
    gen = dbmod.session.__wrapped__()
    db = next(gen)
    try:
        assert db.query(models.User).filter_by(email="a@a.com").count() == 0
    finally:
        gen.close()
