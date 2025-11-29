"""add_additional_performance_indexes

Revision ID: 74e866cd0826
Revises: 111b10f3261e
Create Date: 2025-11-28 15:36:21.489236

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "74e866cd0826"
down_revision: Union[str, None] = "111b10f3261e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add additional performance indexes for complex queries."""

    # ===== فهارس للبحث النصي في المنشورات =====
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

        # فهرس GIN للبحث السريع في محتوى المنشورات
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posts_content_gin 
            ON posts USING gin(content gin_trgm_ops)
        """
        )
    except Exception as e:
        print(f"Warning: Could not create text search index: {e}")

    # ===== فهارس مركبة للاستعلامات المعقدة =====

    # فهرس للبحث في منشورات مستخدم معين حسب التاريخ
    op.create_index(
        "idx_posts_owner_created_published",
        "posts",
        ["owner_id", "created_at", "published"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس للتعليقات حسب المنشور والتاريخ
    op.create_index(
        "idx_comments_post_created",
        "comments",
        ["post_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس للتعليقات الفرعية
    op.create_index(
        "idx_comments_parent_created",
        "comments",
        ["parent_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # ===== فهارس للإشعارات =====

    # فهرس للإشعارات غير المقروءة لمستخدم
    op.create_index(
        "idx_notifications_user_unread_created",
        "notifications",
        ["user_id", "is_read", "created_at"],
        postgresql_using="btree",
        postgresql_where=sa.text("is_read = false"),
        if_not_exists=True,
    )

    # فهرس لحالة الإشعارات
    op.create_index(
        "idx_notifications_user_status_created",
        "notifications",
        ["user_id", "status", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # ===== فهارس للرسائل =====

    # فهرس للمحادثات
    op.create_index(
        "idx_messages_conversation_timestamp",
        "messages",
        ["conversation_id", "timestamp"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس للرسائل غير المقروءة
    op.create_index(
        "idx_messages_conversation_unread",
        "messages",
        ["conversation_id", "is_read"],
        postgresql_using="btree",
        postgresql_where=sa.text("is_read = false"),
        if_not_exists=True,
    )

    # ===== فهارس للمجتمعات =====

    # فهرس لأعضاء المجتمع
    op.create_index(
        "idx_community_members_community_joined",
        "community_members",
        ["community_id", "join_date"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس للمجتمعات النشطة
    op.create_index(
        "idx_communities_is_active",
        "communities",
        ["is_active"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس لتاريخ إنشاء المجتمعات
    op.create_index(
        "idx_communities_created_at",
        "communities",
        ["created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس لمالك المجتمع
    op.create_index(
        "idx_communities_owner_id",
        "communities",
        ["owner_id"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # ===== فهارس للهاشتاجات =====

    # فهرس لاسم الهاشتاج (للبحث) - مع lowercase
    op.create_index(
        "idx_hashtags_name_lower",
        "hashtags",
        [sa.text("LOWER(name)")],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # ملاحظة: usage_count غير موجود في model، لذا لن نضيف فهرس له

    # ===== فهارس للمتابعة =====

    # فهرس مركب للمتابع والمتابَع
    op.create_index(
        "idx_follows_follower_followed_created",
        "follows",
        ["follower_id", "followed_id", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # ===== فهارس للـ Conversations =====

    # فهرس لنوع المحادثة
    op.create_index(
        "idx_conversations_type",
        "conversations",
        ["type"],
        postgresql_using="btree",
        if_not_exists=True,
    )

    # فهرس للمحادثات النشطة
    op.create_index(
        "idx_conversations_is_active",
        "conversations",
        ["is_active"],
        postgresql_using="btree",
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove additional performance indexes."""

    # حذف جميع الفهارس
    op.execute("DROP INDEX IF EXISTS idx_posts_content_gin")
    op.drop_index(
        "idx_posts_owner_created_published", table_name="posts", if_exists=True
    )
    op.drop_index("idx_comments_post_created", table_name="comments", if_exists=True)
    op.drop_index("idx_comments_parent_created", table_name="comments", if_exists=True)
    op.drop_index(
        "idx_notifications_user_unread_created",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_index(
        "idx_notifications_user_status_created",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_index(
        "idx_messages_conversation_timestamp", table_name="messages", if_exists=True
    )
    op.drop_index(
        "idx_messages_conversation_unread", table_name="messages", if_exists=True
    )
    op.drop_index(
        "idx_community_members_community_joined",
        table_name="community_members",
        if_exists=True,
    )
    op.drop_index("idx_communities_is_active", table_name="communities", if_exists=True)
    op.drop_index(
        "idx_communities_created_at", table_name="communities", if_exists=True
    )
    op.drop_index("idx_communities_owner_id", table_name="communities", if_exists=True)
    op.drop_index("idx_hashtags_name_lower", table_name="hashtags", if_exists=True)
    op.drop_index(
        "idx_follows_follower_followed_created", table_name="follows", if_exists=True
    )
    op.drop_index("idx_conversations_type", table_name="conversations", if_exists=True)
    op.drop_index(
        "idx_conversations_is_active", table_name="conversations", if_exists=True
    )
