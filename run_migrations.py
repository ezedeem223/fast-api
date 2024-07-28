# run_migrations.py

from alembic.config import Config
from alembic import command

if __name__ == "__main__":
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
