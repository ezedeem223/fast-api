"""SQLAlchemy models and enums for the users domain."""

from __future__ import annotations

import enum
from datetime import timedelta

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Text,
    JSON,
    Interval,
    LargeBinary,
    Float,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB as PG_JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy import Enum as SQLAlchemyEnum

from app.core.database import Base
from app.core.db_defaults import timestamp_default
from app.modules.users.associations import post_mentions, user_hashtag_follows


def _array_type(item_type):
    """
    Return an ARRAY type that automatically falls back to JSON for SQLite.
    """
    base = PG_ARRAY(item_type)
    return base.with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


def _jsonb_type():
    """
    Return a JSONB type that stores JSON on SQLite.
    """
    return PG_JSONB().with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


class UserType(str, enum.Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PrivacyLevel(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    CUSTOM = "custom"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class User(Base):
    """Application user model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    phone_number = Column(String)
    is_verified = Column(Boolean, default=False)
    social_credits = Column(Float, default=0.0, index=True, nullable=False)
    verification_document = Column(String, nullable=True)
    otp_secret = Column(String, nullable=True)
    is_2fa_enabled = Column(Boolean, default=False)
    role = Column(
        SQLAlchemyEnum(UserRole, name="user_role_enum"), default=UserRole.USER
    )
    profile_image = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    website = Column(String, nullable=True)
    joined_at = Column(DateTime, server_default=timestamp_default())
    privacy_level = Column(
        SQLAlchemyEnum(PrivacyLevel, name="privacy_level_enum"),
        default=PrivacyLevel.PUBLIC,
    )
    custom_privacy = Column(JSON, default={})
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)
    skills = Column(_array_type(String), nullable=True)
    interests = Column(_array_type(String), nullable=True)
    ui_settings = Column(_jsonb_type(), default={})
    notifications_settings = Column(_jsonb_type(), default={})
    user_type = Column(
        SQLAlchemyEnum(UserType, name="user_type_enum"), default=UserType.PERSONAL
    )
    business_name = Column(String, nullable=True)
    business_registration_number = Column(String, nullable=True)
    bank_account_info = Column(String, nullable=True)
    id_document_url = Column(String, nullable=True)
    passport_url = Column(String, nullable=True)
    business_document_url = Column(String, nullable=True)
    selfie_url = Column(String, nullable=True)
    hide_read_status = Column(Boolean, default=False)
    verification_status = Column(
        SQLAlchemyEnum(VerificationStatus, name="verification_status_enum"),
        default=VerificationStatus.PENDING,
    )
    is_verified_business = Column(Boolean, default=False)
    public_key = Column(LargeBinary)
    followers_visibility = Column(
        SQLAlchemyEnum("public", "private", "custom", name="followers_visibility_enum"),
        default="public",
    )
    followers_custom_visibility = Column(JSON, default={})
    followers_sort_preference = Column(String, default="date")
    post_count = Column(Integer, default=0)
    interaction_count = Column(Integer, default=0)
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    followers_growth = Column(_array_type(Integer), default=list)
    comment_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    last_warning_date = Column(DateTime(timezone=True), nullable=True)
    ban_count = Column(Integer, default=0)
    current_ban_end = Column(DateTime(timezone=True), nullable=True)
    total_ban_duration = Column(Interval, default=timedelta())
    total_reports = Column(Integer, default=0)
    valid_reports = Column(Integer, default=0)
    allow_reposts = Column(Boolean, default=True)
    last_logout = Column(DateTime, nullable=True)
    current_token = Column(String, nullable=True)
    facebook_id = Column(String, unique=True, nullable=True)
    twitter_id = Column(String, unique=True, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    reputation_score = Column(Float, default=0.0)
    is_suspended = Column(Boolean, default=False)
    preferred_language = Column(String, default="ar")
    auto_translate = Column(Boolean, default=True)
    suspension_end_date = Column(DateTime, nullable=True)
    language = Column(String, nullable=False, default="en")

    token_blacklist = relationship("TokenBlacklist", back_populates="user")
    posts = relationship("Post", back_populates="owner", cascade="all, delete-orphan")
    comments = relationship(
        "Comment", back_populates="owner", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report",
        foreign_keys="Report.reporter_id",
        back_populates="reporter",
        cascade="all, delete-orphan",
    )
    reports_received = relationship(
        "Report",
        foreign_keys="Report.reported_user_id",
        back_populates="reported_user",
        cascade="all, delete-orphan",
    )
    followers = relationship(
        "Follow",
        back_populates="followed",
        foreign_keys="[Follow.followed_id]",
        cascade="all, delete-orphan",
    )
    following = relationship(
        "Follow",
        back_populates="follower",
        foreign_keys="[Follow.follower_id]",
        cascade="all, delete-orphan",
    )
    sent_messages = relationship(
        "Message",
        foreign_keys="[Message.sender_id]",
        back_populates="sender",
        cascade="all, delete-orphan",
    )
    received_messages = relationship(
        "Message",
        foreign_keys="[Message.receiver_id]",
        back_populates="receiver",
        cascade="all, delete-orphan",
    )
    owned_communities = relationship(
        "Community", back_populates="owner", cascade="all, delete-orphan"
    )
    community_memberships = relationship(
        "CommunityMember", back_populates="user", cascade="all, delete-orphan"
    )
    blocks = relationship(
        "Block",
        foreign_keys="[Block.blocker_id]",
        back_populates="blocker",
        cascade="all, delete-orphan",
    )
    blocked_by = relationship(
        "Block",
        foreign_keys="[Block.blocked_id]",
        back_populates="blocked",
        cascade="all, delete-orphan",
    )
    reels = relationship("Reel", back_populates="owner", cascade="all, delete-orphan")
    articles = relationship(
        "Article", back_populates="author", cascade="all, delete-orphan"
    )
    sent_invitations = relationship(
        "CommunityInvitation",
        foreign_keys="[CommunityInvitation.inviter_id]",
        back_populates="inviter",
    )
    received_invitations = relationship(
        "CommunityInvitation",
        foreign_keys="[CommunityInvitation.invitee_id]",
        back_populates="invitee",
    )
    login_sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    statistics = relationship("UserStatistics", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")
    sticker_packs = relationship("StickerPack", back_populates="creator")
    outgoing_calls = relationship(
        "Call", foreign_keys="[Call.caller_id]", back_populates="caller"
    )
    incoming_calls = relationship(
        "Call", foreign_keys="[Call.receiver_id]", back_populates="receiver"
    )
    screen_shares = relationship("ScreenShareSession", back_populates="sharer")
    encrypted_sessions = relationship(
        "EncryptedSession",
        back_populates="user",
        foreign_keys="[EncryptedSession.user_id]",
    )
    votes = relationship("Vote", back_populates="user")
    followed_hashtags = relationship(
        "Hashtag", secondary=user_hashtag_follows, back_populates="followers"
    )
    reactions = relationship(
        "Reaction", back_populates="user", cascade="all, delete-orphan"
    )
    block_logs_given = relationship(
        "BlockLog", foreign_keys="[BlockLog.blocker_id]", back_populates="blocker"
    )
    block_logs_received = relationship(
        "BlockLog", foreign_keys="[BlockLog.blocked_id]", back_populates="blocked"
    )
    block_appeals = relationship(
        "BlockAppeal", foreign_keys="[BlockAppeal.user_id]", back_populates="user"
    )
    mentions = relationship(
        "Post", secondary=post_mentions, back_populates="mentioned_users"
    )
    outgoing_encrypted_calls = relationship(
        "EncryptedCall",
        foreign_keys="[EncryptedCall.caller_id]",
        back_populates="caller",
    )
    incoming_encrypted_calls = relationship(
        "EncryptedCall",
        foreign_keys="[EncryptedCall.receiver_id]",
        back_populates="receiver",
    )
    search_history = relationship("SearchStatistics", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    amenhotep_analytics = relationship("AmenhotepChatAnalytics", back_populates="user")
    social_accounts = relationship("SocialMediaAccount", back_populates="user")
    social_posts = relationship("SocialMediaPost", back_populates="user")
    activities = relationship("UserActivity", back_populates="user")
    events = relationship("UserEvent", back_populates="user")
    ip_bans_created = relationship("IPBan", back_populates="created_by_user")
    banned_words_created = relationship("BannedWord", back_populates="created_by_user")
    poll_votes = relationship("PollVote", back_populates="user")
    notification_preferences = relationship(
        "NotificationPreferences", back_populates="user", uselist=False
    )
    amenhotep_messages = relationship("AmenhotepMessage", back_populates="user")


class TokenBlacklist(Base):
    """Blacklisted tokens to invalidate sessions."""

    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    blacklisted_on = Column(DateTime, default=timestamp_default())
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="token_blacklist")


class UserActivity(Base):
    """Track high-level user activities."""

    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    activity_type = Column(String)
    timestamp = Column(DateTime, default=timestamp_default())
    details = Column(JSON)

    user = relationship("User", back_populates="activities")


class UserEvent(Base):
    """Log granular user events."""

    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    event_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="events")


class UserSession(Base):
    """Active login sessions."""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, unique=True, index=True)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    last_activity = Column(DateTime(timezone=True), server_default=timestamp_default())

    user = relationship("User", back_populates="login_sessions")


class UserStatistics(Base):
    """Daily user statistics snapshot."""

    __tablename__ = "user_statistics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    post_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)

    user = relationship("User", back_populates="statistics")


# === [ADDITION START] ===
class Badge(Base):
    """Represents an expertise badge definition (e.g., 'Python Expert')."""

    __tablename__ = "badges"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)  # e.g., "Coding Guru"
    description = Column(String)
    category = Column(String)  # e.g., "Technology", "Cooking"
    level = Column(Integer, default=1)  # 1=Novice, 2=Intermediate, 3=Expert
    icon_url = Column(String, nullable=True)

    # Thresholds required to earn this badge automatically
    required_posts = Column(Integer, default=0)
    required_score = Column(Float, default=0.0)


class UserBadge(Base):
    """Link between users and the badges they have earned."""

    __tablename__ = "user_badges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    badge_id = Column(Integer, ForeignKey("badges.id", ondelete="CASCADE"))
    earned_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    user = relationship("User", backref="earned_badges")
    badge = relationship("Badge")


# === [ADDITION END] ===

__all__ = [
    "UserType",
    "VerificationStatus",
    "PrivacyLevel",
    "UserRole",
    "post_mentions",
    "user_hashtag_follows",
    "User",
    "TokenBlacklist",
    "UserActivity",
    "UserEvent",
    "UserSession",
    "UserStatistics",
    "Badge",
    "UserBadge",
]
