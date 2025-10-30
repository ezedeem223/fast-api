from typing import Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def _engine_kwargs(database_url: str) -> Dict:
    """Return engine kwargs tailored for the selected backend."""

    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": 20,
        "max_overflow": 40,
    }


SQLALCHEMY_DATABASE_URL = settings.sqlalchemy_database_uri


engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs(SQLALCHEMY_DATABASE_URL))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
