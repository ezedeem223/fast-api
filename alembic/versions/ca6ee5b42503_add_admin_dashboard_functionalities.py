"""Add admin dashboard functionalities

Revision ID: ca6ee5b42503
Revises: 39f2bbdc24e5
Create Date: 2024-10-05 13:56:00.984456

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ca6ee5b42503"
down_revision: Union[str, None] = "39f2bbdc24e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create UserRole enum
    user_role = postgresql.ENUM("ADMIN", "MODERATOR", "USER", name="userrole")
    user_role.create(op.get_bind())

    # Add role column to users table
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("ADMIN", "MODERATOR", "USER", name="userrole"),
            nullable=False,
            server_default="USER",
        ),
    )

    # Add statistics table for admin dashboard
    op.create_table(
        "statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("total_users", sa.Integer(), nullable=False),
        sa.Column("total_posts", sa.Integer(), nullable=False),
        sa.Column("total_communities", sa.Integer(), nullable=False),
        sa.Column("total_reports", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_statistics_date"), "statistics", ["date"], unique=False)


def downgrade() -> None:
    # Drop statistics table
    op.drop_index(op.f("ix_statistics_date"), table_name="statistics")
    op.drop_table("statistics")

    # Remove role column from users table
    op.drop_column("users", "role")

    # Drop UserRole enum
    op.execute("DROP TYPE userrole")
