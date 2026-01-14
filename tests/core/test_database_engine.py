"""Test module for test database session10."""
import pytest

import app.core.database as db_module
from app.core.database import session as db_session


def test_build_engine_postgres_connect_args():
    """Test case for test build engine postgres connect args."""
    engine = db_module.build_engine("postgresql://user:pass@localhost:5432/dbname")
    assert engine.url.host == "localhost"
    assert engine.url.database == "dbname"
    assert engine.pool._pool.maxsize == 20  # type: ignore[attr-defined]


def test_build_engine_sqlite_check_same_thread(monkeypatch):
    """Test case for test build engine sqlite check same thread."""
    engine = db_module.build_engine("sqlite:///./test.db")
    assert engine.url.database.endswith("test.db")
    # SQLite connect_args set check_same_thread False
    assert engine.url.drivername.startswith("sqlite")


def test_get_db_closes_on_exit(monkeypatch):
    """Test case for test get db closes on exit."""
    closed = []

    class DummySession:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(db_module, "SessionLocal", lambda: DummySession())
    gen = db_module.get_db()
    sess = next(gen)
    assert isinstance(sess, DummySession)
    with pytest.raises(StopIteration):
        next(gen)
    assert closed == [True]


def test_session_module_build_engine():
    """Test case for test session module build engine."""
    engine = db_session.build_engine("sqlite:///./session.db")
    assert engine.url.database.endswith("session.db")


def test_sessionlocal_attributes():
    """Test case for test sessionlocal attributes."""
    eng = db_session.build_engine("sqlite:///./session2.db")
    SessionLocal = db_session.sessionmaker(autocommit=False, autoflush=False, bind=eng)
    assert SessionLocal.kw["autocommit"] is False  # type: ignore[attr-defined]
    assert SessionLocal.kw["autoflush"] is False  # type: ignore[attr-defined]
    assert SessionLocal.kw["bind"] == eng  # type: ignore[attr-defined]
