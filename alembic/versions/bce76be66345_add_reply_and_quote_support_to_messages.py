"""Add reply and quote support to messages

Revision ID: bce76be66345
Revises: afe7d58e94ea
Create Date: 2024-10-10 18:46:24.476392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bce76be66345'
down_revision: Union[str, None] = 'afe7d58e94ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('messages', sa.Column('replied_to_id', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('quoted_message_id', sa.Integer(), nullable=True))
    op.alter_column('messages', 'content',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=True)
    op.create_foreign_key(None, 'messages', 'messages', ['replied_to_id'], ['id'])
    op.create_foreign_key(None, 'messages', 'messages', ['quoted_message_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'messages', type_='foreignkey')
    op.drop_constraint(None, 'messages', type_='foreignkey')
    op.alter_column('messages', 'content',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(),
               existing_nullable=True)
    op.drop_column('messages', 'quoted_message_id')
    op.drop_column('messages', 'replied_to_id')
    # ### end Alembic commands ###
