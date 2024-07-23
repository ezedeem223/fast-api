"""add content column to posts table

Revision ID: 64165d709839
Revises: ddb1305c3adc
Create Date: 2024-07-22 21:14:27.936810

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "64165d709839"
down_revision: Union[str, None] = "ddb1305c3adc"
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
