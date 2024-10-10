"""Add read status and privacy settings

Revision ID: 82b239ec69eb
Revises: 533038e4f110
Create Date: 2024-10-10 19:12:26.816046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82b239ec69eb'
down_revision: Union[str, None] = '533038e4f110'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('messages', sa.Column('is_read', sa.Boolean(), nullable=True))
    op.add_column('messages', sa.Column('read_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('hide_read_status', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'hide_read_status')
    op.drop_column('messages', 'read_at')
    op.drop_column('messages', 'is_read')
    # ### end Alembic commands ###
