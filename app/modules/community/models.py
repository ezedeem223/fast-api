"""Community domain SQLAlchemy models and enums.

Models cover communities, invitations/membership/roles, tags/categories, search stats/suggestions,
and archives (reels/articles/digital museum items)."""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy import Enum as SAEnum

from app.core.database import Base
from app.core.db_defaults import timestamp_default
from .associations import community_tags


class CommunityRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    VIP = "vip"
    MEMBER = "member"


class CommunityCategory(Base):
    """High-level category grouping for communities."""

    __tablename__ = "community_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    category = relationship("Category", back_populates="community_categories")
    communities = relationship("Community", back_populates="community_category")


class Community(Base):
    """Community owned by a user and optionally tied to a category."""

    __tablename__ = "communities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    is_active = Column(Boolean, default=True)
    community_category_id = Column(
        Integer, ForeignKey("community_categories.id"), nullable=True
    )
    is_private = Column(Boolean, default=False)
    requires_approval = Column(Boolean, default=False)
    language = Column(String, nullable=False, default="en")
    is_temporary = Column(
        Boolean, default=False, doc="Marks the community as instant/temporary"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When this community will be auto-dissolved",
    )
    community_category = relationship("CommunityCategory", back_populates="communities")

    owner = relationship("User", back_populates="owned_communities")
    members = relationship("CommunityMember", back_populates="community")
    posts = relationship(
        "Post",
        back_populates="community",
        cascade="all, delete-orphan",
        foreign_keys="[Post.community_id]",
    )
    reels = relationship(
        "Reel", back_populates="community", cascade="all, delete-orphan"
    )
    articles = relationship(
        "Article", back_populates="community", cascade="all, delete-orphan"
    )
    invitations = relationship(
        "CommunityInvitation", back_populates="community", cascade="all, delete-orphan"
    )
    rules = relationship(
        "CommunityRule", back_populates="community", cascade="all, delete-orphan"
    )
    statistics = relationship(
        "CommunityStatistics", back_populates="community", cascade="all, delete-orphan"
    )
    tags = relationship("Tag", secondary=community_tags, back_populates="communities")

    @property
    def category(self):
        """Expose the primary category directly."""
        return self.community_category.category if self.community_category else None

    @property
    def member_count(self) -> int:
        """Return the number of members associated with the community."""
        return len(self.members)


class CommunityMember(Base):
    """Membership association between users and communities."""

    __tablename__ = "community_members"
    __table_args__ = {"extend_existing": True}

    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(
        SAEnum(CommunityRole, name="community_role_enum"),
        nullable=False,
        default=CommunityRole.MEMBER,
    )
    join_date = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    activity_score = Column(Integer, default=0)

    user = relationship("User", back_populates="community_memberships")
    community = relationship("Community", back_populates="members")


class CommunityStatistics(Base):
    """Daily aggregate statistics for a community."""

    __tablename__ = "community_statistics"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    date = Column(Date, nullable=False)
    member_count = Column(Integer, default=0)
    post_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    total_reactions = Column(Integer, default=0)
    average_posts_per_user = Column(Float, default=0.0)

    community = relationship("Community", back_populates="statistics")

    __table_args__ = (
        UniqueConstraint("community_id", "date", name="uix_community_date"),
    )


class CommunityRule(Base):
    """Rules governing acceptable behaviour within a community."""

    __tablename__ = "community_rules"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    rule = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=timestamp_default(),
        onupdate=timestamp_default(),
    )

    community = relationship("Community", back_populates="rules")


class CommunityInvitation(Base):
    """Invitation for a user to join a community."""

    __tablename__ = "community_invitations"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="CASCADE"))
    inviter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    invitee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    community = relationship("Community", back_populates="invitations")
    inviter = relationship(
        "User", foreign_keys=[inviter_id], back_populates="sent_invitations"
    )
    invitee = relationship(
        "User", foreign_keys=[invitee_id], back_populates="received_invitations"
    )


class Category(Base):
    """Top-level category used by the catalogue/search flows."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)

    community_categories = relationship("CommunityCategory", back_populates="category")


class SearchSuggestion(Base):
    """Cached suggestion derived from popular search queries."""

    __tablename__ = "search_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String, unique=True, nullable=False)
    usage_count = Column(Integer, default=0)
    last_used = Column(DateTime(timezone=True), server_default=timestamp_default())


class SearchStatistics(Base):
    """Aggregated statistics for search behaviour."""

    __tablename__ = "search_statistics"
    __table_args__ = (
        UniqueConstraint("user_id", "term", name="uq_search_statistics_user_term"),
        Index("ix_search_statistics_term", "term"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    term = Column(String, nullable=False)
    searches = Column(Integer, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=timestamp_default(),
        onupdate=timestamp_default(),
    )

    user = relationship("User", back_populates="search_history")


class Tag(Base):
    """Simple tag assigned to communities."""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    communities = relationship(
        "Community",
        secondary=community_tags,
        back_populates="tags",
    )


class Reel(Base):
    """Short video reel entity owned by a user."""

    __tablename__ = "reels"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    video_url = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    view_count = Column(Integer, default=0)

    owner = relationship("User", back_populates="reels")
    community = relationship("Community", back_populates="reels")


class ArchivedReel(Base):
    """Archived copy of expired reels for audit/history."""

    __tablename__ = "archived_reels"

    id = Column(Integer, primary_key=True, index=True)
    reel_id = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    video_url = Column(String, nullable=False)
    description = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    view_count = Column(Integer, default=0)
    archived_at = Column(DateTime(timezone=True), server_default=timestamp_default())


class Article(Base):
    """Long-form article shared within communities."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    author_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )

    author = relationship("User", back_populates="articles")
    community = relationship("Community", back_populates="articles")


# ==========================================
# ==========================================
class CommunityVoteDelegation(Base):
    """
    Allows a user to delegate their voting power to another user within a community.
    Supports Liquid Democracy.
    """

    __tablename__ = "community_vote_delegations"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    grantor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User giving the vote",
    )
    grantee_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User receiving the vote",
    )

    # Scope can be 'global' (all votes in community) or specific to a 'category'
    scope = Column(String, default="global", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=timestamp_default())

    grantor = relationship(
        "User", foreign_keys=[grantor_id], backref="delegated_votes_given"
    )
    grantee = relationship(
        "User", foreign_keys=[grantee_id], backref="delegated_votes_received"
    )
    community = relationship("Community")


# ==========================================
# ==========================================
class CommunityArchive(Base):
    """Represents a digital archive or museum for the community."""

    __tablename__ = "community_archives"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=timestamp_default())

    items = relationship(
        "DigitalMuseumItem", back_populates="archive", cascade="all, delete-orphan"
    )


class DigitalMuseumItem(Base):
    """An artifact or item within a community archive."""

    __tablename__ = "digital_museum_items"

    id = Column(Integer, primary_key=True, index=True)
    archive_id = Column(
        Integer, ForeignKey("community_archives.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String, nullable=False)
    media_url = Column(String, nullable=False)
    historical_context = Column(
        Text, nullable=True, doc="Story or history behind this item"
    )
    curated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at = Column(TIMESTAMP(timezone=True), server_default=timestamp_default())

    archive = relationship("CommunityArchive", back_populates="items")
    curated_by_user = relationship("User", foreign_keys=[curated_by])
