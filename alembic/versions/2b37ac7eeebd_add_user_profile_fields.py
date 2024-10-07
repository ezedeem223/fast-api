"""add_user_profile_fields

Revision ID: 2b37ac7eeebd
Revises: 8b586e6d71e8
Create Date: 2024-10-06 22:02:05.595010

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b37ac7eeebd"
down_revision: Union[str, None] = "8b586e6d71e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_image", sa.String(), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("location", sa.String(), nullable=True))
    op.add_column("users", sa.Column("website", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("joined_at", sa.DateTime(), server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_column("users", "joined_at")
    op.drop_column("users", "website")
    op.drop_column("users", "location")
    op.drop_column("users", "bio")
    op.drop_column("users", "profile_image")
