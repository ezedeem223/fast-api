"""add living memory post relation table

Revision ID: e63a77b4848a
Revises: 74e866cd0826
Create Date: 2025-11-29 22:00:06.424690

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e63a77b4848a"
down_revision: Union[str, None] = "74e866cd0826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands to create the new table only ###
    op.create_table(
        "post_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_post_id", sa.Integer(), nullable=False),
        sa.Column("target_post_id", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_post_relations_id"), "post_relations", ["id"], unique=False
    )
    op.create_index(
        "ix_post_relations_source_target",
        "post_relations",
        ["source_post_id", "target_post_id"],
        unique=True,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands to revert the changes ###
    op.drop_index("ix_post_relations_source_target", table_name="post_relations")
    op.drop_index(op.f("ix_post_relations_id"), table_name="post_relations")
    op.drop_table("post_relations")
    # ### end Alembic commands ###
