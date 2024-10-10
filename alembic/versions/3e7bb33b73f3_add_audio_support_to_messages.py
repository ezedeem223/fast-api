"""Add audio support to messages

Revision ID: 3e7bb33b73f3
Revises: 7f2427d3b2ec
Create Date: 2024-10-10 03:23:15.418237

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3e7bb33b73f3"
down_revision: Union[str, None] = "7f2427d3b2ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    # Создание перечисления UserType
    user_type = postgresql.ENUM("PERSONAL", "BUSINESS", name="usertype")
    user_type.create(op.get_bind())

    # Создание перечисления VerificationStatus
    verification_status = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", name="verificationstatus"
    )
    verification_status.create(op.get_bind())

    op.add_column("messages", sa.Column("audio_url", sa.String(), nullable=True))
    op.add_column("messages", sa.Column("duration", sa.Float(), nullable=True))
    op.alter_column("messages", "content", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column(
        "users",
        "user_type",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum("PERSONAL", "BUSINESS", name="usertype"),
        postgresql_using="user_type::usertype",
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "verification_status",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum("PENDING", "APPROVED", "REJECTED", name="verificationstatus"),
        postgresql_using="verification_status::verificationstatus",
        existing_nullable=True,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "users",
        "verification_status",
        existing_type=sa.Enum(
            "PENDING", "APPROVED", "REJECTED", name="verificationstatus"
        ),
        type_=sa.VARCHAR(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "user_type",
        existing_type=sa.Enum("PERSONAL", "BUSINESS", name="usertype"),
        type_=sa.VARCHAR(length=50),
        existing_nullable=True,
    )
    op.alter_column("messages", "content", existing_type=sa.VARCHAR(), nullable=False)
    op.drop_column("messages", "duration")
    op.drop_column("messages", "audio_url")

    # Удаление перечислений
    user_type = postgresql.ENUM("PERSONAL", "BUSINESS", name="usertype")
    user_type.drop(op.get_bind())
    verification_status = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", name="verificationstatus"
    )
    verification_status.drop(op.get_bind())
    # ### end Alembic commands ###
