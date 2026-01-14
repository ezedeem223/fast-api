"""Phase8 admin + moderation enhancements.

- Add audit_logs table for admin actions.
- Add is_regex flag to banned_words.
- Add archived_reels table for expired reel archival.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c9f2f9f3c0a"
down_revision = "b1b2337d4c2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Helper for upgrade."""
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("TIMEZONE('utc', now())")),
    )

    op.add_column(
        "banned_words",
        sa.Column("is_regex", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "archived_reels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("reel_id", sa.Integer(), nullable=False, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("video_url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("community_id", sa.Integer(), sa.ForeignKey("communities.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0"),
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.text("TIMEZONE('utc', now())")),
    )


def downgrade() -> None:
    """Helper for downgrade."""
    op.drop_table("archived_reels")
    op.drop_column("banned_words", "is_regex")
    op.drop_table("audit_logs")
