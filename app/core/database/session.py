"""Database engine and session management utilities.

- Builds per-backend engine kwargs (SQLite vs Postgres) with safe pooling defaults.
- Derives the URL from settings, using the test database automatically when APP_ENV=test.
- Exposes a SessionLocal factory and a scoped `get_db` dependency with guaranteed cleanup.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _engine_kwargs(database_url: str) -> dict:
    """Return engine keyword arguments tuned per backend (SQLite vs pooled Postgres)."""
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        return {
            "pool_pre_ping": True,
            "connect_args": {"check_same_thread": False},
            "poolclass": NullPool,
        }
    return {
        "pool_pre_ping": True,
        "pool_size": 100,
        "max_overflow": 200,
        "pool_recycle": 300,
    }


def build_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine using application settings by default.

    Respects APP_ENV=test by choosing the test DSN to protect production data.
    """
    if database_url is None:
        use_test_url = settings.environment.lower() == "test"
        database_url = settings.get_database_url(use_test=use_test_url)
    return create_engine(database_url, **_engine_kwargs(database_url))


engine: Engine = build_engine()

if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _add_sqlite_functions(dbapi_connection, connection_record):
        """Provide SQLite equivalents for PostgreSQL functions used in defaults."""

        def _now():
            return datetime.now(timezone.utc).isoformat(" ")

        dbapi_connection.create_function("now", 0, _now)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    """Yield a database session with guaranteed cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
