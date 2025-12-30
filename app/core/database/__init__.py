"""Core database access helpers with optimized connection pooling.

Provides a pooled engine + SessionLocal for app use, plus a `get_db` dependency that
guarantees cleanup. Kept for compatibility alongside `app.core.database.session`.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.models.base import Base


def build_engine(database_url: str):
    """Construct a SQLAlchemy engine with pooling tuned per backend."""
    connect_args = {}
    if "postgresql" in database_url:
        connect_args = {
            "options": "-c timezone=utc",
            "application_name": "fastapi_app",
            "connect_timeout": 10,
        }
    elif "sqlite" in database_url:
        connect_args = {"check_same_thread": False}

    return create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        echo_pool=False,
        pool_reset_on_return="rollback",
        connect_args=connect_args,
    )


if hasattr(settings, "database_url") and settings.database_url:
    SQLALCHEMY_DATABASE_URL = str(settings.database_url)
else:
    # Backfill a DSN from discrete env pieces when DATABASE_URL is not provided.
    if all(
        [
            settings.database_username,
            settings.database_password,
            settings.database_hostname,
            settings.database_name,
        ]
    ):
        SQLALCHEMY_DATABASE_URL = (
            f"postgresql://{settings.database_username}:{settings.database_password}"
            f"@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
        )
    else:
        # Fail open to local SQLite so the app can start (health checks) when env vars are missing.
        SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

# Application engine
engine = build_engine(SQLALCHEMY_DATABASE_URL)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Provide a database session with guaranteed close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


try:
    from .query_helpers import (
        optimize_comment_query,
        optimize_post_query,
        optimize_user_query,
        paginate_query,
        with_joined_loads,
        with_select_loads,
    )

    __all__ = [
        "Base",
        "SessionLocal",
        "engine",
        "get_db",
        "build_engine",
        "with_joined_loads",
        "with_select_loads",
        "paginate_query",
        "optimize_post_query",
        "optimize_comment_query",
        "optimize_user_query",
    ]
except ImportError:
    # Fallback if query_helpers.py is missing
    __all__ = ["Base", "SessionLocal", "engine", "get_db", "build_engine"]
