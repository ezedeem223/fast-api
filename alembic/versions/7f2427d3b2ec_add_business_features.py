"""Add business features

Revision ID: 7f2427d3b2ec
Revises: 21afbf87a734
Create Date: 2024-10-10 00:50:30.667100

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f2427d3b2ec"
down_revision: Union[str, None] = "21afbf87a734"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "business_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_user_id", sa.Integer(), nullable=True),
        sa.Column("client_user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["business_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_transactions_id"),
        "business_transactions",
        ["id"],
        unique=False,
    )
    op.add_column("users", sa.Column("user_type", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("business_name", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("business_registration_number", sa.String(), nullable=True)
    )
    op.add_column("users", sa.Column("bank_account_info", sa.String(), nullable=True))
    op.add_column("users", sa.Column("id_document_url", sa.String(), nullable=True))
    op.add_column("users", sa.Column("passport_url", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("business_document_url", sa.String(), nullable=True)
    )
    op.add_column("users", sa.Column("selfie_url", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("verification_status", sa.String(50), nullable=True)
    )
    op.add_column(
        "users", sa.Column("is_verified_business", sa.Boolean(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "is_verified_business")
    op.drop_column("users", "verification_status")
    op.drop_column("users", "selfie_url")
    op.drop_column("users", "business_document_url")
    op.drop_column("users", "passport_url")
    op.drop_column("users", "id_document_url")
    op.drop_column("users", "bank_account_info")
    op.drop_column("users", "business_registration_number")
    op.drop_column("users", "business_name")
    op.drop_column("users", "user_type")
    op.drop_index(
        op.f("ix_business_transactions_id"), table_name="business_transactions"
    )
    op.drop_table("business_transactions")
    # ### end Alembic commands ###
