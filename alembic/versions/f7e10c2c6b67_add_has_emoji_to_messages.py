"""Add has_emoji flag to messages

Revision ID: f7e10c2c6b67
Revises: 8c9f2f9f3c0a
Create Date: 2026-01-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7e10c2c6b67"
down_revision: Union[str, None] = "8c9f2f9f3c0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("has_emoji", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("messages", "has_emoji", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "has_emoji")

