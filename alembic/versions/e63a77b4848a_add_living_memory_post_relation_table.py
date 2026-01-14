"""add living memory post relation table (noop)

Revision ID: e63a77b4848a
Revises: 74e866cd0826
Create Date: 2025-11-29 22:00:06.424690
"""

from typing import Sequence, Union

revision: str = "e63a77b4848a"
down_revision: Union[str, None] = "74e866cd0826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Helper for upgrade."""
    pass


def downgrade() -> None:
    """Helper for downgrade."""
    pass
