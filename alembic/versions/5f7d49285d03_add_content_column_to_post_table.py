"""add content column to post table

Revision ID: 5f7d49285d03
Revises: 99e5c5184e17
Create Date: 2024-07-29 10:03:42.823925

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f7d49285d03"
down_revision: Union[str, None] = "99e5c5184e17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "posts",
        sa.Column(
            "content",
            sa.String(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("posts", "content")
    pass
