"""Alembic configuration.

Loads metadata from the shared Base, wires the database URL from env (prefers ALEMBIC_DATABASE_URL,
then DATABASE_URL, then test URL), and runs migrations in offline/online modes.
"""

import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from app.models.base import Base  # Import shared declarative base
import app.models  # noqa: F401 - ensure models are imported for metadata population
from app.core.config import settings

# Set the target metadata for Alembic migrations
target_metadata = [Base.metadata]

config = context.config
# Configure the SQLAlchemy URL using settings
db_url = (
    os.getenv("ALEMBIC_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or settings.get_database_url(use_test=True)
)
config.set_main_option("sqlalchemy.url", db_url)

# Configure logging if a config file is provided
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Reset target_metadata (already set above)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    This configures the context with a URL and does not require an Engine.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    This creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


# Decide whether to run migrations in offline or online mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
