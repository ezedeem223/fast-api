"""Add conversation statistics

Revision ID: d3dbe9cc995d
Revises: a93d039c77a3
Create Date: 2024-10-13 07:31:14.322811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3dbe9cc995d'
down_revision: Union[str, None] = 'a93d039c77a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('conversation_statistics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=True),
    sa.Column('total_messages', sa.Integer(), nullable=True),
    sa.Column('total_time', sa.Integer(), nullable=True),
    sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('user1_id', sa.Integer(), nullable=True),
    sa.Column('user2_id', sa.Integer(), nullable=True),
    sa.Column('total_files', sa.Integer(), nullable=True),
    sa.Column('total_emojis', sa.Integer(), nullable=True),
    sa.Column('total_stickers', sa.Integer(), nullable=True),
    sa.Column('total_response_time', sa.Float(), nullable=True),
    sa.Column('total_responses', sa.Integer(), nullable=True),
    sa.Column('average_response_time', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user1_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user2_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_statistics_conversation_id'), 'conversation_statistics', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_conversation_statistics_id'), 'conversation_statistics', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_conversation_statistics_id'), table_name='conversation_statistics')
    op.drop_index(op.f('ix_conversation_statistics_conversation_id'), table_name='conversation_statistics')
    op.drop_table('conversation_statistics')
    # ### end Alembic commands ###
