import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base

previous_remote_dsn = (
    f"postgresql://{settings.database_username}:"
    f"{settings.database_password}@"
    f"{settings.database_hostname}:"
    f"{settings.database_port}/"
    f"{settings.database_name}_test"
)

# Default to Postgres test DB; allow override via LOCAL_TEST_DATABASE_URL if needed.
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "LOCAL_TEST_DATABASE_URL",
    previous_remote_dsn,
)

engine_kwargs = {"echo": False}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def session():
    """Reset tables between tests using fast TRUNCATE for Postgres or DELETE for SQLite."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            table_names = ", ".join([f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables])
            if table_names:
                connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        else:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
