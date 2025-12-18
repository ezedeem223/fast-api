"""add_additional_performance_indexes (noop after initial schema)

Revision ID: 74e866cd0826
Revises: 111b10f3261e
Create Date: 2025-11-28 15:36:21.489236
"""

from typing import Sequence, Union

revision: str = "74e866cd0826"
down_revision: Union[str, None] = "111b10f3261e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
