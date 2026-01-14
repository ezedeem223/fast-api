"""additional domain tables (noop; schema captured in initial full)

Revision ID: a1f9dce2add
Revises: c57c0be8e270
Create Date: 2025-12-03 00:00:00.000000
"""

from typing import Sequence, Union

revision: str = "a1f9dce2add"
down_revision: Union[str, None] = "c57c0be8e270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Helper for upgrade."""
    pass


def downgrade() -> None:
    """Helper for downgrade."""
    pass
