"""Add community statistics

Revision ID: 3299985d305f
Revises: 1849c26ba5d1
Create Date: 2024-10-05 18:41:45.345095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3299985d305f'
down_revision: Union[str, None] = '1849c26ba5d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('community_statistics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('community_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('member_count', sa.Integer(), nullable=True),
    sa.Column('post_count', sa.Integer(), nullable=True),
    sa.Column('comment_count', sa.Integer(), nullable=True),
    sa.Column('active_users', sa.Integer(), nullable=True),
    sa.Column('total_reactions', sa.Integer(), nullable=True),
    sa.Column('average_posts_per_user', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['community_id'], ['communities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('community_id', 'date', name='uix_community_date')
    )
    op.create_index(op.f('ix_community_statistics_id'), 'community_statistics', ['id'], unique=False)
    op.drop_index('ix_statistics_date', table_name='statistics')
    op.drop_table('statistics')
    op.alter_column('communities', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('true'))
    op.alter_column('reports', 'status',
               existing_type=postgresql.ENUM('PENDING', 'REVIEWED', 'RESOLVED', name='reportstatus'),
               nullable=True,
               existing_server_default=sa.text("'PENDING'::reportstatus"))
    op.alter_column('users', 'role',
               existing_type=postgresql.ENUM('ADMIN', 'MODERATOR', 'USER', name='userrole'),
               nullable=True,
               existing_server_default=sa.text("'USER'::userrole"))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'role',
               existing_type=postgresql.ENUM('ADMIN', 'MODERATOR', 'USER', name='userrole'),
               nullable=False,
               existing_server_default=sa.text("'USER'::userrole"))
    op.alter_column('reports', 'status',
               existing_type=postgresql.ENUM('PENDING', 'REVIEWED', 'RESOLVED', name='reportstatus'),
               nullable=False,
               existing_server_default=sa.text("'PENDING'::reportstatus"))
    op.alter_column('communities', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('true'))
    op.create_table('statistics',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('total_users', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_posts', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_communities', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_reports', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('date', sa.DATE(), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='statistics_pkey')
    )
    op.create_index('ix_statistics_date', 'statistics', ['date'], unique=False)
    op.drop_index(op.f('ix_community_statistics_id'), table_name='community_statistics')
    op.drop_table('community_statistics')
    # ### end Alembic commands ###
