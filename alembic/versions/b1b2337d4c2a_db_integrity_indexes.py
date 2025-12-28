"""Add integrity indexes for follows and search statistics

Revision ID: b1b2337d4c2a
Revises: d8399df38143
Create Date: 2025-12-22 14:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1b2337d4c2a"
down_revision: Union[str, None] = "d8399df38143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_follows_followed_id", "follows", ["followed_id"], unique=False)
    op.create_index("ix_follows_follower_id", "follows", ["follower_id"], unique=False)
    op.create_index(
        "ix_search_statistics_term", "search_statistics", ["term"], unique=False
    )
    op.create_unique_constraint(
        "uq_search_statistics_user_term",
        "search_statistics",
        ["user_id", "term"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_search_statistics_user_term", "search_statistics", type_="unique")
    op.drop_index("ix_search_statistics_term", table_name="search_statistics")
    op.drop_index("ix_follows_follower_id", table_name="follows")
    op.drop_index("ix_follows_followed_id", table_name="follows")
