"""add_performance_indexes (noop after initial schema)**

Revision ID: 111b10f3261e
Revises: d8399df38143
Create Date: 2025-11-26 17:28:40.872120
"""

from typing import Sequence, Union

revision: str = "111b10f3261e"
down_revision: Union[str, None] = "d8399df38143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Indexes are already in the initial_full_schema migration.
    """Helper for upgrade."""
    pass


def downgrade() -> None:
    """Helper for downgrade."""
    pass
