"""Add soft-delete columns to posts.

Revision ID: 9d4b6f7c1a2e
Revises: c4c5c0e3b3c4
Create Date: 2026-01-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d4b6f7c1a2e"
down_revision = "c4c5c0e3b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "posts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("posts", "deleted_at")
    op.drop_column("posts", "is_deleted")
