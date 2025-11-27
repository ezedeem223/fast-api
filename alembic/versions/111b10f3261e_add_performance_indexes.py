"""add_performance_indexes

Revision ID: 111b10f3261e
Revises: 5254a93363d9
Create Date: 2025-11-26 17:28:40.872120

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "111b10f3261e"
down_revision: Union[str, None] = "5254a93363d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes for frequently queried columns."""

    # Posts table indexes
    op.create_index(
        "idx_posts_owner_id_created_at",
        "posts",
        ["owner_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_posts_community_id_created_at",
        "posts",
        ["community_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_posts_published_created_at",
        "posts",
        ["published", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_posts_is_archived",
        "posts",
        ["is_archived"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # Comments table indexes
    op.create_index(
        "idx_comments_post_id_created_at",
        "comments",
        ["post_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_comments_owner_id_created_at",
        "comments",
        ["owner_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_comments_parent_id_created_at",
        "comments",
        ["parent_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_comments_is_pinned",
        "comments",
        ["is_pinned"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # Reactions table composite indexes
    op.create_index(
        "idx_reactions_user_post",
        "reactions",
        ["user_id", "post_id"],
        postgresql_using="btree",
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "idx_reactions_user_comment",
        "reactions",
        ["user_id", "comment_id"],
        postgresql_using="btree",
        unique=True,
        if_not_exists=True,
    )

    # Messages table indexes
    # تم حذف الفهارس التي تسبب مشاكل (created_at غير موجود)
    # نحتفظ فقط بفهرس حالة القراءة إذا كان العمود موجوداً (is_read)
    # بناءً على الكود، is_read موجود كـ Boolean default=False
    op.create_index(
        "idx_messages_is_read",
        "messages",
        ["is_read"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # Notifications table indexes
    op.create_index(
        "idx_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_notifications_status",
        "notifications",
        ["status"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_notifications_is_read",
        "notifications",
        ["is_read"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # Follow table indexes
    op.create_index(
        "idx_follow_follower_id",
        "follows",
        ["follower_id"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_follow_followed_id",
        "follows",
        ["followed_id"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    op.create_index(
        "idx_follow_follower_followed",
        "follows",
        ["follower_id", "followed_id"],
        postgresql_using="btree",
        unique=True,
        if_not_exists=True,
    )

    op.create_index(
        "idx_users_email",
        "users",
        ["email"],
        postgresql_using="btree",
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "idx_users_is_verified",
        "users",
        ["is_verified"],
        postgresql_using="btree",
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove performance indexes."""

    # Drop all indexes created in upgrade
    op.drop_index("idx_posts_owner_id_created_at", table_name="posts", if_exists=True)
    op.drop_index(
        "idx_posts_community_id_created_at", table_name="posts", if_exists=True
    )
    op.drop_index("idx_posts_published_created_at", table_name="posts", if_exists=True)
    op.drop_index("idx_posts_is_archived", table_name="posts", if_exists=True)

    op.drop_index(
        "idx_comments_post_id_created_at", table_name="comments", if_exists=True
    )
    op.drop_index(
        "idx_comments_owner_id_created_at", table_name="comments", if_exists=True
    )
    op.drop_index(
        "idx_comments_parent_id_created_at", table_name="comments", if_exists=True
    )
    op.drop_index("idx_comments_is_pinned", table_name="comments", if_exists=True)

    op.drop_index("idx_reactions_user_post", table_name="reactions", if_exists=True)
    op.drop_index("idx_reactions_user_comment", table_name="reactions", if_exists=True)

    # حذفنا الفهارس المقابلة لما حذفناه في upgrade
    op.drop_index("idx_messages_is_read", table_name="messages", if_exists=True)

    op.drop_index(
        "idx_notifications_user_id_created_at",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_index(
        "idx_notifications_status", table_name="notifications", if_exists=True
    )
    op.drop_index(
        "idx_notifications_is_read", table_name="notifications", if_exists=True
    )

    op.drop_index("idx_follow_follower_id", table_name="follows", if_exists=True)
    op.drop_index("idx_follow_followed_id", table_name="follows", if_exists=True)
    op.drop_index("idx_follow_follower_followed", table_name="follows", if_exists=True)

    op.drop_index("idx_users_email", table_name="users", if_exists=True)
    op.drop_index("idx_users_is_verified", table_name="users", if_exists=True)
