from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


# Configure the database connection URL using settings, with graceful fallbacks for tests.
SQLALCHEMY_DATABASE_URL = settings.database_url


def _build_engine():
    """Create the SQLAlchemy engine with sensible defaults for both Postgres and SQLite."""

    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=20,
        max_overflow=20,
    )


# Create the SQLAlchemy engine.
engine = _build_engine()

# Create a session factory for generating database sessions.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the base class for declarative models.
Base = declarative_base()


def get_db():
    """
    Dependency generator for obtaining a database session.

    Yields:
        A SQLAlchemy Session instance.

    Ensures that the session is closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
