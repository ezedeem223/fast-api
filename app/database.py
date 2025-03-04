from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

# Configure the database connection URL using settings.
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.database_username}:{settings.database_password}"
    f"@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
)

# Create the SQLAlchemy engine with a connection pool.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=100,  # Number of connections in the pool.
    max_overflow=200,  # Additional connections allowed beyond the pool size.
)

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
