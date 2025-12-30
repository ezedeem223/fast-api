"""Post domain SQLAlchemy models and enums.

Includes posts/comments/reactions, poll entities, social media postings, and living memory relations.
Uses array/jsonb columns that gracefully degrade to JSON on SQLite for tests.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import TSVECTOR as PG_TSVECTOR
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP

from app.core.database import Base
from app.core.db_defaults import timestamp_default
from app.modules.users.associations import post_mentions


def _array_type(item_type):
    """
    Return an ARRAY type that gracefully falls back to JSON on SQLite.
    """
    base = PG_ARRAY(item_type)
    return base.with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


def _jsonb_type():
    """
    Return a JSONB type stored as JSON on SQLite.
    """
    return PG_JSONB().with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


def _tsvector_type():
    """
    Provide a TSVector column that degrades to TEXT for SQLite.
    """
    return (
        PG_TSVECTOR().with_variant(Text, "sqlite").with_variant(Text, "sqlite+pysqlite")
    )


post_hashtags = Table(
    "post_hashtags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE")),
    Column("hashtag_id", Integer, ForeignKey("hashtags.id", ondelete="CASCADE")),
)


class CopyrightType(str, enum.Enum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


class SocialMediaType(str, enum.Enum):
    REDDIT = "reddit"
    LINKEDIN = "linkedin"


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class ReactionType(str, enum.Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class Reaction(Base):
    """Reaction on posts or comments."""

    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    reaction_type = Column(
        Enum("like", "love", "haha", "wow", "sad", "angry", name="reaction_type"),
        nullable=False,
    )

    user = relationship("User", back_populates="reactions")
    post = relationship("Post", back_populates="reactions")
    comment = relationship("Comment", back_populates="reactions")

    __table_args__ = (
        Index("ix_reactions_user_id", "user_id"),
        Index("ix_reactions_post_id", "post_id"),
        Index("ix_reactions_comment_id", "comment_id"),
    )


class Comment(Base):
    """Comment entity for posts."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    parent_id = Column(
        Integer,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    image_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    sticker_id = Column(
        Integer, ForeignKey("stickers.id", ondelete="SET NULL"), nullable=True
    )
    language = Column(String, nullable=False, default="en")
    is_edited = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)
    contains_profanity = Column(Boolean, default=False)
    has_invalid_urls = Column(Boolean, default=False)
    reported_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    is_highlighted = Column(Boolean, default=False)
    is_best_answer = Column(Boolean, default=False)
    has_emoji = Column(Boolean, default=False)
    has_sticker = Column(Boolean, default=False)
    sentiment_score = Column(Float, nullable=True)
    sentiment = Column(String, nullable=True)
    is_pinned = Column(Boolean, default=False)
    pinned_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="comments", foreign_keys=[owner_id])
    post = relationship("Post", back_populates="comments", foreign_keys=[post_id])
    parent = relationship(
        "Comment",
        remote_side="Comment.id",
        back_populates="replies",
        foreign_keys=[parent_id],
    )
    replies = relationship(
        "Comment",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    reactions = relationship(
        "Reaction", back_populates="comment", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="comment", cascade="all, delete-orphan"
    )
    edit_history = relationship(
        "CommentEditHistory",
        back_populates="comment",
        cascade="all, delete-orphan",
    )
    sticker = relationship(
        "Sticker", back_populates="comments", foreign_keys=[sticker_id]
    )

    __table_args__ = (
        Index("ix_comments_post_id", "post_id"),
        Index("ix_comments_owner_id", "owner_id"),
        Index("ix_comments_parent_id", "parent_id"),
    )


class Post(Base):
    """Primary post entity."""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    published = Column(Boolean, server_default="True", nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=True
    )
    votes = Column(Integer, default=0)
    media_url = Column(String)
    media_type = Column(String)
    media_text = Column(Text)
    is_safe_content = Column(Boolean, default=True)
    language = Column(String, nullable=False, default="en")
    is_short_video = Column(Boolean, default=False)
    has_best_answer = Column(Boolean, default=False)
    comment_count = Column(Integer, default=0)
    max_pinned_comments = Column(Integer, default=3)
    category_id = Column(Integer, ForeignKey("post_categories.id"), nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    is_published = Column(Boolean, default=False)
    original_post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    is_repost = Column(Boolean, default=False)
    repost_count = Column(Integer, default=0)
    allow_reposts = Column(Boolean, default=True)
    sentiment = Column(String)
    sentiment_score = Column(Float)
    content_suggestion = Column(String)
    is_audio_post = Column(Boolean, default=False)
    audio_url = Column(String, nullable=True)
    is_poll = Column(Boolean, default=False)
    is_help_request = Column(Boolean, default=False)
    copyright_type = Column(
        Enum(CopyrightType), nullable=False, default=CopyrightType.ALL_RIGHTS_RESERVED
    )
    custom_copyright = Column(String, nullable=True)
    is_archived = Column(Boolean, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)
    search_vector = Column(_tsvector_type())
    share_scope = Column(String, default="public")
    shared_with_community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="SET NULL"), nullable=True
    )
    # [Privacy First]
    is_encrypted = Column(Boolean, default=False)
    encryption_key_id = Column(
        String,
        nullable=True,
        doc="ID of the key used, managed by Key Management System",
    )

    # [Collective Memory]
    is_living_testimony = Column(
        Boolean, default=False, doc="Is this post a documented living testimony?"
    )
    score = Column(Float, default=0.0, index=True)
    quality_score = Column(Float, default=0.0)
    originality_score = Column(Float, default=0.0)
    sharing_settings = Column(_jsonb_type(), default={})

    __table_args__ = (
        Index("idx_post_search_vector", "search_vector", postgresql_using="gin"),
        Index("idx_title_user", "title", "owner_id"),
    )

    owner = relationship("User", back_populates="posts", foreign_keys=[owner_id])
    reactions = relationship(
        "Reaction", back_populates="post", cascade="all, delete-orphan"
    )
    original_post = relationship("Post", remote_side=[id], backref="reposts")
    mentioned_users = relationship(
        "User", secondary=post_mentions, back_populates="mentions"
    )
    hashtags = relationship("Hashtag", secondary=post_hashtags)
    comments = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    community = relationship(
        "Community", back_populates="posts", foreign_keys=[community_id]
    )
    reports = relationship(
        "Report", back_populates="post", cascade="all, delete-orphan"
    )
    votes_rel = relationship(
        "Vote", back_populates="post", cascade="all, delete-orphan"
    )
    repost_stats = relationship(
        "RepostStatistics", uselist=False, back_populates="post"
    )
    poll_options = relationship("PollOption", back_populates="post")
    poll = relationship("Poll", back_populates="post", uselist=False)
    category = relationship("PostCategory", back_populates="posts")
    vote_statistics = relationship(
        "PostVoteStatistics",
        back_populates="post",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PostVoteStatistics(Base):
    """Vote statistics for a post."""

    __tablename__ = "post_vote_statistics"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"))
    total_votes = Column(Integer, default=0)
    upvotes = Column(Integer, default=0)
    downvotes = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    love_count = Column(Integer, default=0)
    haha_count = Column(Integer, default=0)
    wow_count = Column(Integer, default=0)
    sad_count = Column(Integer, default=0)
    angry_count = Column(Integer, default=0)
    last_updated = Column(
        DateTime(timezone=True),
        server_default=timestamp_default(),
        onupdate=timestamp_default(),
    )

    post = relationship("Post", back_populates="vote_statistics")


class RepostStatistics(Base):
    """Repost statistics per post."""

    __tablename__ = "repost_statistics"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    repost_count = Column(Integer, default=0)
    community_shares = Column(Integer, default=0)
    views_after_repost = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    last_reposted = Column(DateTime, default=timestamp_default())

    post = relationship("Post", back_populates="repost_stats")


class PollOption(Base):
    """Option entry for a poll."""

    __tablename__ = "poll_options"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_text = Column(String, nullable=False)
    post = relationship("Post", back_populates="poll_options")
    votes = relationship("PollVote", back_populates="option")


class Poll(Base):
    """Poll attached to a post."""

    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), unique=True)
    end_date = Column(DateTime)
    post = relationship("Post", back_populates="poll")


class PollVote(Base):
    """Vote cast for a poll option."""

    __tablename__ = "poll_votes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_id = Column(Integer, ForeignKey("poll_options.id"))

    user = relationship("User", back_populates="poll_votes")
    post = relationship("Post")
    option = relationship("PollOption", back_populates="votes")


class PostCategory(Base):
    """Hierarchical category for posts."""

    __tablename__ = "post_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    parent_id = Column(
        Integer,
        ForeignKey(
            "post_categories.id",
            use_alter=True,
            name="fk_postcategories_parent_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )

    posts = relationship("Post", back_populates="category")
    children = relationship(
        "PostCategory", back_populates="parent", cascade="all, delete-orphan"
    )
    parent = relationship("PostCategory", back_populates="children", remote_side=[id])


class SocialMediaAccount(Base):
    """Linked social media account."""

    __tablename__ = "social_media_accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    platform = Column(Enum(SocialMediaType))
    access_token = Column(String)
    refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True))
    account_username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())

    user = relationship("User", back_populates="social_accounts")
    posts = relationship("SocialMediaPost", back_populates="account")


class SocialMediaPost(Base):
    """Post shared through a linked social account."""

    __tablename__ = "social_media_posts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    account_id = Column(Integer, ForeignKey("social_media_accounts.id"))
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    platform_post_id = Column(String, nullable=True)
    media_urls = Column(_array_type(String), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(PostStatus), default=PostStatus.DRAFT)
    error_message = Column(Text, nullable=True)
    post_metadata = Column(_jsonb_type(), default={})
    engagement_stats = Column(_jsonb_type(), default={})
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    published_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="social_posts")
    account = relationship("SocialMediaAccount", back_populates="posts")


class PostRelation(Base):
    """
    Living Memory System: Stores semantic or temporal connections between posts.
    """

    __tablename__ = "post_relations"

    id = Column(Integer, primary_key=True, index=True)
    source_post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    target_post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )

    similarity_score = Column(Float, default=0.0)

    relation_type = Column(String, default="semantic", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    source_post = relationship(
        "Post", foreign_keys=[source_post_id], backref="related_memories"
    )

    target_post = relationship(
        "Post", foreign_keys=[target_post_id], backref="cited_in_memories"
    )

    __table_args__ = (
        Index(
            "ix_post_relations_source_target",
            "source_post_id",
            "target_post_id",
            unique=True,
        ),
    )


# ==========================================
# ==========================================
class LivingTestimony(Base):
    """
    Specialized model for verified oral histories or testimonies.
    Linked to a Post that contains the media/text.
    """

    __tablename__ = "living_testimonies"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), unique=True)
    verified_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    historical_event = Column(
        String, nullable=True, doc="The event this testimony relates to"
    )
    geographic_location = Column(String, nullable=True)
    recorded_at = Column(DateTime(timezone=True))

    post = relationship("Post", backref="testimony_metadata")
    verifier = relationship("User")


__all__ = [
    "CopyrightType",
    "SocialMediaType",
    "PostStatus",
    "ReactionType",
    "Reaction",
    "Post",
    "PostVoteStatistics",
    "RepostStatistics",
    "PollOption",
    "Poll",
    "PollVote",
    "PostCategory",
    "SocialMediaAccount",
    "SocialMediaPost",
    "post_hashtags",
    "PostRelation",
    "LivingTestimony",
]
