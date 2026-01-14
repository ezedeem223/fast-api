"""Test module for database."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base


def _resolve_test_db_url() -> str:
    """Helper for  resolve test db url."""
    explicit = os.environ.get("LOCAL_TEST_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL"
    )
    if explicit:
        return explicit
    try:
        return settings.get_database_url(use_test=True)
    except Exception as exc:
        raise RuntimeError(
            "Test database is not configured. Set LOCAL_TEST_DATABASE_URL, "
            "TEST_DATABASE_URL, or DATABASE_URL/DATABASE_* for a Postgres *_test database."
        ) from exc


SQLALCHEMY_DATABASE_URL = _resolve_test_db_url()
try:
    parsed_url = make_url(SQLALCHEMY_DATABASE_URL)
except Exception as exc:
    raise RuntimeError(f"Invalid test database URL: {exc}") from exc

if not parsed_url.drivername.startswith("postgresql"):
    raise RuntimeError(
        f"Tests require Postgres, got '{parsed_url.drivername}'. "
        "Set LOCAL_TEST_DATABASE_URL/TEST_DATABASE_URL to a Postgres *_test database."
    )
if not parsed_url.database or not parsed_url.database.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against non-test database '{parsed_url.database}'. "
        "Set LOCAL_TEST_DATABASE_URL/TEST_DATABASE_URL to a dedicated *_test database."
    )

engine_kwargs = {
    "echo": False,
    "connect_args": {"connect_timeout": 5},
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _db_clean_strategy() -> str:
    """Helper for  db clean strategy."""
    override = os.getenv("TEST_DB_CLEAN_STRATEGY", "").lower()
    if override in {"truncate", "delete"}:
        return override
    host = engine.url.host or ""
    if host and host not in {"localhost", "127.0.0.1"}:
        return "delete"
    return "truncate"


@pytest.fixture(scope="function")
def session():
    """Reset tables between tests using fast TRUNCATE for Postgres."""
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        if _db_clean_strategy() == "truncate":
            table_names = ", ".join(
                [f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables]
            )
            if table_names:
                try:
                    connection.execute(
                        text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
                    )
                except Exception:
                    for table in reversed(Base.metadata.sorted_tables):
                        connection.execute(table.delete())
        else:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
