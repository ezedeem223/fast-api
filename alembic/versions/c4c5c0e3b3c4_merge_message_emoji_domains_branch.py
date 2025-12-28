"""Merge heads for message emoji and domains branch

Revision ID: c4c5c0e3b3c4
Revises: f7e10c2c6b67, a1f9dce2add
Create Date: 2026-01-04 00:10:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c4c5c0e3b3c4"
down_revision: Union[str, tuple[str, ...], None] = ("f7e10c2c6b67", "a1f9dce2add")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge."""
    pass


def downgrade() -> None:
    """Split branches back (no-op)."""
    pass

