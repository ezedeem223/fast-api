"""Add privacy settings to User model

Revision ID: cfb3370b5e15
Revises: ba8a5216b091
Create Date: 2024-10-07 19:58:06.901371

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cfb3370b5e15"
down_revision: Union[str, None] = "ba8a5216b091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    privacylevel = postgresql.ENUM("PUBLIC", "PRIVATE", "CUSTOM", name="privacylevel")
    privacylevel.create(op.get_bind())

    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column(
            "privacy_level",
            sa.Enum("PUBLIC", "PRIVATE", "CUSTOM", name="privacylevel"),
            nullable=True,
        ),
    )
    op.add_column(
        "users", sa.Column("custom_privacy", postgresql.JSONB(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "custom_privacy")
    op.drop_column("users", "privacy_level")
    # ### end Alembic commands ###

    privacylevel = postgresql.ENUM("PUBLIC", "PRIVATE", "CUSTOM", name="privacylevel")
    privacylevel.drop(op.get_bind())
