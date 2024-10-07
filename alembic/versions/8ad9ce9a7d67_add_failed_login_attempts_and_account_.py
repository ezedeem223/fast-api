"""Add failed login attempts and account locking

Revision ID: 8ad9ce9a7d67
Revises: cfb3370b5e15
Create Date: 2024-10-07 20:49:58.663229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8ad9ce9a7d67'
down_revision: Union[str, None] = 'cfb3370b5e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.String(), nullable=True),
    sa.Column('ip_address', sa.String(), nullable=True),
    sa.Column('user_agent', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('last_activity', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_sessions_id'), 'user_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_user_sessions_session_id'), 'user_sessions', ['session_id'], unique=True)
    op.add_column('users', sa.Column('last_login', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('account_locked_until', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('users', 'custom_privacy',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'custom_privacy',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True)
    op.drop_column('users', 'account_locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'last_login')
    op.drop_index(op.f('ix_user_sessions_session_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    # ### end Alembic commands ###
