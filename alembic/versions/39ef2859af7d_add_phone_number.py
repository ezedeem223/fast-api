"""add phone number

Revision ID: 39ef2859af7d
Revises: 178f39c1b4b5
Create Date: 2024-07-29 10:36:28.928083
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "39ef2859af7d"
down_revision: Union[str, None] = "178f39c1b4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "phone_number", sa.String(length=20), nullable=True
        ),  # Adjust length if needed
    )


def downgrade() -> None:
    op.drop_column("users", "phone_number")
