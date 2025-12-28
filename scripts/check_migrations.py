"""CI helper to validate Alembic migrations on a clean SQLite database.

Usage:
    python scripts/check_migrations.py
"""

import os
from pathlib import Path
from sqlalchemy.engine import make_url

from alembic.config import main as alembic_main


def main() -> None:
    temp_db = Path(".alembic_ci.db")
    os.environ.setdefault("APP_ENV", "test")

    db_url = (
        os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("TEST_DATABASE_URL")
        or f"sqlite:///{temp_db}"
    )

    url = make_url(db_url)
    if url.drivername.startswith("sqlite"):
        print(
            "[check_migrations] Skipping migration run on SQLite "
            "(uses unsupported ARRAY types). Set ALEMBIC_DATABASE_URL to a Postgres URL to enable."
        )
        return

    os.environ["ALEMBIC_DATABASE_URL"] = db_url
    os.environ["DATABASE_URL"] = db_url
    os.environ["TEST_DATABASE_URL"] = db_url

    # Ensure a clean slate for file-based SQLite only (not used for PG)
    if temp_db.exists():
        temp_db.unlink()

    # Run migrations up to all heads (merges supported)
    alembic_main(argv=["upgrade", "heads"])

    # Cleanup the temporary database
    if temp_db.exists():
        temp_db.unlink()


if __name__ == "__main__":
    main()
