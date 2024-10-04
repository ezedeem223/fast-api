"""Add community roles and activity score

Revision ID: ae81654ec6df
Revises: ab4e170c9526
Create Date: 2024-10-04 13:02:41.781798

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ae81654ec6df"
down_revision: Union[str, None] = "ab4e170c9526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    op.execute(
        "CREATE TYPE communityrole AS ENUM ('OWNER', 'ADMIN', 'MODERATOR', 'VIP', 'MEMBER')"
    )

    # Now add the column using the created enum type
    op.add_column(
        "community_members",
        sa.Column(
            "role",
            sa.Enum(
                "OWNER", "ADMIN", "MODERATOR", "VIP", "MEMBER", name="communityrole"
            ),
            nullable=False,
            server_default="MEMBER",
        ),
    )
    op.add_column(
        "community_members",
        sa.Column(
            "join_date",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "community_members",
        sa.Column("activity_score", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("community_members", "activity_score")
    op.drop_column("community_members", "join_date")
    op.drop_column("community_members", "role")

    # Drop the enum type
    op.execute("DROP TYPE communityrole")
