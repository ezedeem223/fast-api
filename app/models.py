"""
models.py - Enhanced version with detailed English comments.
This file contains the SQLAlchemy models for the social media platform.
It includes definitions for users, posts, comments, notifications, and more,
along with association tables to manage many-to-many relationships.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Index,
    Enum,
    Text,
    DateTime,
    UniqueConstraint,
    Date,
    Float,
    Table,
    JSON,
    ARRAY,
    LargeBinary,
    Interval,
    Time,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql import func
from .database import Base
import enum
from datetime import date, timedelta
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy import Enum as SQLAlchemyEnum

# -------------------------
# Association Tables
# -------------------------
# These tables are used to model many-to-many relationships.

# Table for linking posts and mentioned users
post_mentions = Table(
    "post_mentions",
    Base.metadata,
    Column(
        "post_id",
        Integer,
        ForeignKey("posts.id", use_alter=True, name="fk_post_mentions_post_id"),
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", use_alter=True, name="fk_post_mentions_user_id"),
    ),
)

# Table for linking communities and tags
community_tags = Table(
    "community_tags",
    Base.metadata,
    Column(
        "community_id",
        Integer,
        ForeignKey(
            "communities.id", use_alter=True, name="fk_community_tags_community_id"
        ),
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", use_alter=True, name="fk_community_tags_tag_id"),
    ),
)

# Table for linking stickers and sticker categories
sticker_category_association = Table(
    "sticker_category_association",
    Base.metadata,
    Column(
        "sticker_id",
        Integer,
        ForeignKey(
            "stickers.id",
            use_alter=True,
            name="fk_sticker_category_association_sticker_id",
        ),
    ),
    Column(
        "category_id",
        Integer,
        ForeignKey(
            "sticker_categories.id",
            use_alter=True,
            name="fk_sticker_category_association_category_id",
        ),
    ),
)

# Table for linking users and hashtags they follow
user_hashtag_follows = Table(
    "user_hashtag_follows",
    Base.metadata,
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", use_alter=True, name="fk_user_hashtag_follows_user_id"),
    ),
    Column(
        "hashtag_id",
        Integer,
        ForeignKey(
            "hashtags.id", use_alter=True, name="fk_user_hashtag_follows_hashtag_id"
        ),
    ),
)

# Table for post hashtags association
post_hashtags = Table(
    "post_hashtags",
    Base.metadata,
    Column(
        "post_id",
        Integer,
        ForeignKey("posts.id", use_alter=True, name="fk_post_hashtags_post_id"),
    ),
    Column(
        "hashtag_id",
        Integer,
        ForeignKey("hashtags.id", use_alter=True, name="fk_post_hashtags_hashtag_id"),
    ),
)

# -------------------------
# Enum Classes Definitions
# -------------------------
# These enumerations define constant values used in various models.


class UserType(str, enum.Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CommunityRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    VIP = "vip"
    MEMBER = "member"


class PrivacyLevel(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    CUSTOM = "custom"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class CallType(str, enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


class CallStatus(str, enum.Enum):
    PENDING = "pending"
    ONGOING = "ongoing"
    ENDED = "ended"


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    STICKER = "sticker"


class ScreenShareStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


class ReactionType(enum.Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class BlockDuration(enum.Enum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


class BlockType(str, enum.Enum):
    FULL = "full"
    PARTIAL_COMMENT = "partial_comment"
    PARTIAL_MESSAGE = "partial_message"


class AppealStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationCategory(str, enum.Enum):
    SYSTEM = "system"
    SOCIAL = "social"
    SECURITY = "security"
    PROMOTIONAL = "promotional"
    COMMUNITY = "community"


class CopyrightType(str, enum.Enum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class SocialMediaType(str, enum.Enum):
    REDDIT = "reddit"
    LINKEDIN = "linkedin"


class NotificationType(str, enum.Enum):
    NEW_FOLLOWER = "new_follower"
    NEW_COMMENT = "new_comment"
    NEW_REACTION = "new_reaction"
    NEW_MESSAGE = "new_message"
    MENTION = "mention"
    POST_SHARE = "post_share"
    COMMUNITY_INVITE = "community_invite"
    REPORT_UPDATE = "report_update"
    ACCOUNT_SECURITY = "account_security"
    SYSTEM_UPDATE = "system_update"


# -------------------------
# Models Definitions
# -------------------------
# Below are the SQLAlchemy models for different entities in the application.


class BlockAppeal(Base):
    """
    Model for block appeals by users.
    """

    __tablename__ = "block_appeals"
    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(
        Integer,
        ForeignKey(
            "blocks.id",
            use_alter=True,
            name="fk_block_appeals_block_id",
            ondelete="CASCADE",
        ),
    )
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            use_alter=True,
            name="fk_block_appeals_user_id",
            ondelete="CASCADE",
        ),
    )
    reason = Column(String, nullable=False)
    status = Column(Enum(AppealStatus), default=AppealStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", use_alter=True, name="fk_block_appeals_reviewer_id"),
        nullable=True,
    )

    # Relationships linking the appeal to the block and users involved.
    block = relationship("Block", back_populates="appeals")
    user = relationship("User", foreign_keys=[user_id], back_populates="block_appeals")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class Hashtag(Base):
    """
    Model for hashtags used in posts.
    """

    __tablename__ = "hashtags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    # Followers relationship is established via the association table.


class Reaction(Base):
    """
    Model for reactions on posts or comments.
    """

    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id", use_alter=True, name="fk_reactions_user_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    post_id = Column(
        Integer,
        ForeignKey(
            "posts.id", use_alter=True, name="fk_reactions_post_id", ondelete="CASCADE"
        ),
        nullable=True,
    )
    comment_id = Column(
        Integer,
        ForeignKey(
            "comments.id",
            use_alter=True,
            name="fk_reactions_comment_id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    reaction_type = Column(Enum(ReactionType), nullable=False)

    # Relationships for linking reaction to user, post, or comment.
    user = relationship("User", back_populates="reactions")
    post = relationship("Post", back_populates="reactions")
    comment = relationship("Comment", back_populates="reactions")

    __table_args__ = (
        Index("ix_reactions_user_id", user_id),
        Index("ix_reactions_post_id", post_id),
        Index("ix_reactions_comment_id", comment_id),
    )


class User(Base):
    """
    Model for application users.
    """

    __tablename__ = "users"
    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    phone_number = Column(String)
    is_verified = Column(Boolean, default=False)
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
    joined_at = Column(DateTime, server_default=func.now())
    privacy_level = Column(
        SQLAlchemyEnum(PrivacyLevel, name="privacy_level_enum"),
        default=PrivacyLevel.PUBLIC,
    )
    custom_privacy = Column(JSON, default={})
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)
    skills = Column(ARRAY(String), nullable=True)
    interests = Column(ARRAY(String), nullable=True)
    ui_settings = Column(JSONB, default={})
    notifications_settings = Column(JSONB, default={})
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
    followers_growth = Column(ARRAY(Integer), default=list)
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

    # Relationships linking User to various entities.
    token_blacklist = relationship("TokenBlacklist", back_populates="user")
    posts = relationship("Post", back_populates="owner", cascade="all, delete-orphan")
    comments = relationship(
        "Comment", back_populates="owner", cascade="all, delete-orphan"
    )
    # تم التعديل هنا لتحديد عمود المفتاح الأجنبي بوضوح لعلاقة التقارير (المستخدم الذي أرسل التقرير)
    reports = relationship(
        "Report",
        foreign_keys="Report.reporter_id",
        back_populates="reporter",
        cascade="all, delete-orphan",
    )
    # إذا كنت ترغب في تعريف علاقات أخرى للتقارير باستخدام أعمدة مفتاح أجنبي مختلفة، يمكن استخدام:
    # reports_reviewed = relationship("Report", foreign_keys="Report.reviewed_by")
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
    # تم التعديل هنا بإضافة foreign_keys لتحديد العمود الصحيح في جدول الجلسات المشفرة.
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


class SocialMediaAccount(Base):
    """
    Model representing a user's social media account details.
    """

    __tablename__ = "social_media_accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    platform = Column(SQLAlchemyEnum(SocialMediaType))
    access_token = Column(String)
    refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True))
    account_username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship linking account to its owner and associated posts.
    user = relationship("User", back_populates="social_accounts")
    posts = relationship("SocialMediaPost", back_populates="account")


class SocialMediaPost(Base):
    """
    Model for social media posts shared via linked social accounts.
    """

    __tablename__ = "social_media_posts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    account_id = Column(Integer, ForeignKey("social_media_accounts.id"))
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    platform_post_id = Column(String, nullable=True)
    media_urls = Column(ARRAY(String), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLAlchemyEnum(PostStatus), default=PostStatus.DRAFT)
    error_message = Column(Text, nullable=True)
    # Renamed column to avoid conflict with reserved keyword.
    post_metadata = Column(JSONB, default={})
    engagement_stats = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships linking social post to its owner and account.
    user = relationship("User", back_populates="social_posts")
    account = relationship("SocialMediaAccount", back_populates="posts")


class UserActivity(Base):
    """
    Model for tracking user activities (e.g., login, post, comment).
    """

    __tablename__ = "user_activities"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    activity_type = Column(String)  # e.g., login, post, comment, report
    timestamp = Column(DateTime, default=func.now())
    details = Column(JSON)

    user = relationship("User", back_populates="activities")


User.activities = relationship("UserActivity", back_populates="user")


class CommunityCategory(Base):
    """
    Model for community categories.
    """

    __tablename__ = "community_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)

    communities = relationship("Community", back_populates="category")


class UserEvent(Base):
    """
    Model for logging events related to users.
    """

    __tablename__ = "user_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    event_type = Column(String, nullable=False)  # e.g., login, post, comment, report
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="events")


User.events = relationship("UserEvent", back_populates="user")


class UserWarning(Base):
    """
    Model for user warnings.
    """

    __tablename__ = "user_warnings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserBan(Base):
    """
    Model for user bans.
    """

    __tablename__ = "user_bans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    duration = Column(Interval, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IPBan(Base):
    """
    Model for IP bans.
    """

    __tablename__ = "ip_bans"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, index=True, nullable=False)
    reason = Column(String)
    banned_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))

    created_by_user = relationship("User", back_populates="ip_bans_created")


User.ip_bans_created = relationship("IPBan", back_populates="created_by_user")


class BannedWord(Base):
    """
    Model for banned words in content.
    """

    __tablename__ = "banned_words"
    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True, nullable=False)
    severity = Column(Enum("warn", "ban", name="word_severity"), default="warn")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by_user = relationship("User", back_populates="banned_words_created")


User.banned_words_created = relationship("BannedWord", back_populates="created_by_user")


class BanStatistics(Base):
    """
    Model for storing ban statistics per day.
    """

    __tablename__ = "ban_statistics"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    total_bans = Column(Integer, default=0)
    ip_bans = Column(Integer, default=0)
    word_bans = Column(Integer, default=0)
    user_bans = Column(Integer, default=0)
    most_common_reason = Column(String)
    effectiveness_score = Column(Float)


class BanReason(Base):
    """
    Model to track reasons for bans and their usage count.
    """

    __tablename__ = "ban_reasons"
    id = Column(Integer, primary_key=True, index=True)
    reason = Column(String, nullable=False)
    count = Column(Integer, default=1)
    last_used = Column(DateTime(timezone=True), server_default=func.now())


class Post(Base):
    """
    Model for posts created by users.
    """

    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    published = Column(Boolean, server_default="True", nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
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
    is_short_video = Column(Boolean, default=False)
    has_best_answer = Column(Boolean, default=False)
    comment_count = Column(Integer, default=0)
    max_pinned_comments = Column(Integer, default=3)
    category_id = Column(Integer, ForeignKey("post_categories.id"), nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    is_published = Column(Boolean, default=False)
    # Self-referential foreign key: use_alter to break circular dependency.
    original_post_id = Column(
        Integer,
        ForeignKey(
            "posts.id",
            use_alter=True,
            name="fk_posts_original_post_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
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
    copyright_type = Column(
        Enum(CopyrightType), nullable=False, default=CopyrightType.ALL_RIGHTS_RESERVED
    )
    custom_copyright = Column(String, nullable=True)
    is_archived = Column(Boolean, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)
    search_vector = Column(TSVECTOR)
    share_scope = Column(String, default="public")  # Options: public, community, group
    shared_with_community_id = Column(
        Integer, ForeignKey("communities.id"), nullable=True
    )
    score = Column(Float, default=0.0, index=True)
    sharing_settings = Column(JSONB, default={})  # Advanced sharing settings

    __table_args__ = (
        Index("idx_post_search_vector", search_vector, postgresql_using="gin"),
        Index("idx_title_user", "title", "owner_id"),
    )

    # Relationships linking post to other entities.
    poll_options = relationship("PollOption", back_populates="post")
    poll = relationship("Poll", back_populates="post", uselist=False)
    category = relationship("PostCategory", back_populates="posts")
    owner = relationship("User", back_populates="posts")
    comments = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    community = relationship("Community", back_populates="posts")
    reports = relationship(
        "Report", back_populates="post", cascade="all, delete-orphan"
    )
    votes_rel = relationship(
        "Vote", back_populates="post", cascade="all, delete-orphan"
    )
    hashtags = relationship("Hashtag", secondary=post_hashtags)
    reactions = relationship(
        "Reaction", back_populates="post", cascade="all, delete-orphan"
    )
    original_post = relationship("Post", remote_side=[id], backref="reposts")
    repost_stats = relationship(
        "RepostStatistics", uselist=False, back_populates="post"
    )
    mentioned_users = relationship(
        "User", secondary=post_mentions, back_populates="mentions"
    )
    vote_statistics = relationship(
        "PostVoteStatistics",
        back_populates="post",
        uselist=False,
        cascade="all, delete-orphan",
    )


class NotificationPreferences(Base):
    """
    Model for storing user notification preferences.
    """

    __tablename__ = "notification_preferences"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    in_app_notifications = Column(Boolean, default=True)
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    categories_preferences = Column(JSONB, default={})
    notification_frequency = Column(
        String, default="realtime"
    )  # Options: realtime, hourly, daily, weekly
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="notification_preferences")


User.notification_preferences = relationship(
    "NotificationPreferences", back_populates="user", uselist=False
)


class NotificationGroup(Base):
    """
    Model for grouping similar notifications.
    """

    __tablename__ = "notification_groups"
    id = Column(Integer, primary_key=True, index=True)
    group_type = Column(String, nullable=False)  # e.g., comment_thread, post_likes
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    count = Column(Integer, default=1)
    sample_notification_id = Column(
        Integer,
        ForeignKey(
            "notifications.id",
            use_alter=True,
            name="fk_notification_groups_sample_notification_id",
        ),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("Notification", back_populates="group")


class TokenBlacklist(Base):
    """
    Model for blacklisted tokens (for logout or security purposes).
    """

    __tablename__ = "token_blacklist"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    blacklisted_on = Column(DateTime, default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="token_blacklist")


class PostVoteStatistics(Base):
    """
    Model to track vote statistics for a post.
    """

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
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    post = relationship("Post", back_populates="vote_statistics")


class RepostStatistics(Base):
    """
    Model to track repost statistics for a post.
    """

    __tablename__ = "repost_statistics"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    repost_count = Column(Integer, default=0)
    community_shares = Column(Integer, default=0)
    views_after_repost = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    last_reposted = Column(DateTime, default=func.now())

    post = relationship("Post", back_populates="repost_stats")


class PollOption(Base):
    """
    Model representing an option in a poll.
    """

    __tablename__ = "poll_options"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_text = Column(String, nullable=False)
    post = relationship("Post", back_populates="poll_options")
    votes = relationship("PollVote", back_populates="option")


class Poll(Base):
    """
    Model for polls attached to posts.
    """

    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), unique=True)
    end_date = Column(DateTime)
    post = relationship("Post", back_populates="poll")


class PollVote(Base):
    """
    Model for votes in polls.
    """

    __tablename__ = "poll_votes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_id = Column(Integer, ForeignKey("poll_options.id"))
    user = relationship("User", back_populates="poll_votes")
    post = relationship("Post")
    option = relationship("PollOption", back_populates="votes")


User.poll_votes = relationship("PollVote", back_populates="user")


class Notification(Base):
    """
    Model for notifications sent to users.
    """

    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(String, nullable=False)
    link = Column(String)
    notification_type = Column(String)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.MEDIUM)
    category = Column(Enum(NotificationCategory), default=NotificationCategory.SYSTEM)
    is_read = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    related_id = Column(Integer)
    # Renamed column to avoid reserved keyword conflict.
    notification_metadata = Column(JSONB, default={})
    group_id = Column(Integer, ForeignKey("notification_groups.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING)
    retry_count = Column(Integer, default=0)
    last_retry = Column(DateTime(timezone=True), nullable=True)
    notification_version = Column(Integer, default=1)
    importance_level = Column(Integer, default=1)
    seen_at = Column(DateTime(timezone=True), nullable=True)
    interaction_count = Column(Integer, default=0)
    custom_data = Column(JSONB, default={})
    device_info = Column(JSONB, nullable=True)
    notification_channel = Column(
        String, default="in_app"
    )  # Options: in_app, email, push
    failure_reason = Column(String, nullable=True)
    batch_id = Column(String, nullable=True)
    priority_level = Column(Integer, default=1)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    delivery_tracking = Column(JSONB, default={})
    retry_strategy = Column(String, nullable=True)  # Options: exponential, linear, etc.
    max_retries = Column(Integer, default=3)
    current_retry_count = Column(Integer, default=0)
    last_retry_timestamp = Column(DateTime(timezone=True), nullable=True)

    # Relationships linking notification with its user and delivery logs/attempts.
    user = relationship("User", back_populates="notifications")
    group = relationship("NotificationGroup", back_populates="notifications")
    analytics = relationship(
        "NotificationAnalytics", back_populates="notification", uselist=False
    )
    delivery_logs = relationship(
        "NotificationDeliveryLog", back_populates="notification"
    )
    delivery_attempts_rel = relationship(
        "NotificationDeliveryAttempt", back_populates="notification"
    )

    __table_args__ = (
        Index("idx_notifications_user_created", "user_id", "created_at"),
        Index("idx_notifications_type", "notification_type"),
        Index("idx_notifications_status", "status"),
    )

    def should_retry(self) -> bool:
        """Check if the notification should be retried"""
        if self.status != NotificationStatus.FAILED:
            return False
        if self.current_retry_count >= self.max_retries:
            return False
        from datetime import datetime, timezone

        if self.expiration_date and datetime.now(timezone.utc) > self.expiration_date:
            return False
        return True

    def get_next_retry_delay(self) -> int:
        """Calculate delay before the next retry attempt"""
        if self.retry_strategy == "exponential":
            return 300 * (2**self.current_retry_count)  # 5 minutes * 2^retry_count
        return 300  # Default delay of 5 minutes


class NotificationDeliveryAttempt(Base):
    """
    Model for logging individual notification delivery attempts.
    """

    __tablename__ = "notification_delivery_attempts"
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    attempt_number = Column(Integer, nullable=False)
    attempt_time = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, nullable=False)  # Options: success, failure
    error_message = Column(String, nullable=True)
    delivery_channel = Column(String, nullable=False)
    response_time = Column(Float)  # In seconds
    # Renamed column to avoid reserved keyword conflict.
    attempt_metadata = Column(JSONB, default={})

    notification = relationship("Notification", back_populates="delivery_attempts_rel")

    __table_args__ = (
        Index(
            "idx_delivery_attempts_notification", "notification_id", "attempt_number"
        ),
    )


class NotificationAnalytics(Base):
    """
    Model for analytics data of notifications.
    """

    __tablename__ = "notification_analytics"
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    delivery_attempts = Column(Integer, default=0)
    first_delivery_attempt = Column(DateTime(timezone=True), server_default=func.now())
    last_delivery_attempt = Column(DateTime(timezone=True), onupdate=func.now())
    successful_delivery = Column(Boolean, default=False)
    delivery_channel = Column(String)
    device_info = Column(JSONB, default={})
    performance_metrics = Column(JSONB, default={})

    notification = relationship("Notification", back_populates="analytics")

    __table_args__ = (
        Index("idx_notification_analytics_notification_id", "notification_id"),
        Index("idx_notification_analytics_successful_delivery", "successful_delivery"),
    )


class NotificationDeliveryLog(Base):
    """
    Model for logging notification delivery details.
    """

    __tablename__ = "notification_delivery_logs"
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    attempt_time = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String)
    error_message = Column(String, nullable=True)
    delivery_channel = Column(String)  # e.g., email, push, websocket

    notification = relationship("Notification", back_populates="delivery_logs")


class Comment(Base):
    """
    Model for comments on posts.
    """

    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, nullable=False)
    content = Column(String, nullable=False)
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Self-referential foreign key: add use_alter to break cycle.
    parent_id = Column(
        Integer,
        ForeignKey(
            "comments.id",
            ondelete="CASCADE",
            use_alter=True,
            name="fk_comments_parent_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    likes_count = Column(Integer, default=0)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)
    contains_profanity = Column(Boolean, default=False)
    has_invalid_urls = Column(Boolean, default=False)
    reported_count = Column(Integer, default=0)
    is_highlighted = Column(Boolean, default=False)
    is_best_answer = Column(Boolean, default=False)
    image_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    has_emoji = Column(Boolean, default=False)
    has_sticker = Column(Boolean, default=False)
    sentiment_score = Column(Float, nullable=True)
    language = Column(String, nullable=False, default="en")
    sticker_id = Column(Integer, ForeignKey("stickers.id"), nullable=True)
    is_pinned = Column(Boolean, default=False)
    pinned_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships linking comment to sticker, owner, post, and nested replies.
    sticker = relationship("Sticker", back_populates="comments")
    owner = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")
    reports = relationship(
        "Report", back_populates="comment", cascade="all, delete-orphan"
    )
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent")
    edit_history = relationship(
        "CommentEditHistory", back_populates="comment", cascade="all, delete-orphan"
    )
    reactions = relationship(
        "Reaction", back_populates="comment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_comments_post_id_created_at", "post_id", "created_at"),
        Index("ix_comments_post_id_likes_count", "post_id", "likes_count"),
    )


class AmenhotepMessage(Base):
    """
    Model for Amenhotep chat messages (AI chat functionality).
    """

    __tablename__ = "amenhotep_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(String, nullable=False)
    response = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="amenhotep_messages")


User.amenhotep_messages = relationship("AmenhotepMessage", back_populates="user")


class AmenhotepChatAnalytics(Base):
    """
    Model for analytics of Amenhotep AI chat sessions.
    """

    __tablename__ = "amenhotep_chat_analytics"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    topics_discussed = Column(ARRAY(String), default=list)
    session_duration = Column(Integer)  # in seconds
    satisfaction_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="amenhotep_analytics")


class PostCategory(Base):
    """
    Model for categorizing posts.
    """

    __tablename__ = "post_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    # Self-referential relationship: add use_alter to break cycle.
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
    is_active = Column(Boolean, default=True)

    children = relationship(
        "PostCategory", back_populates="parent", cascade="all, delete-orphan"
    )
    parent = relationship("PostCategory", back_populates="children", remote_side=[id])
    posts = relationship("Post", back_populates="category")


class CommentEditHistory(Base):
    """
    Model to store the edit history of comments.
    """

    __tablename__ = "comment_edit_history"
    id = Column(Integer, primary_key=True, nullable=False)
    # تعديل هنا لإضافة use_alter=True واسم القيد لتفادي مشاكل drop_all
    comment_id = Column(
        Integer,
        ForeignKey(
            "comments.id",
            use_alter=True,
            name="fk_comment_edit_history_comment_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    previous_content = Column(String, nullable=False)
    edited_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    comment = relationship("Comment", back_populates="edit_history")
    __table_args__ = (Index("ix_comment_edit_history_comment_id", "comment_id"),)


class BusinessTransaction(Base):
    """
    Model for business transactions between users.
    """

    __tablename__ = "business_transactions"
    id = Column(Integer, primary_key=True, index=True)
    business_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    business_user = relationship("User", foreign_keys=[business_user_id])
    client_user = relationship("User", foreign_keys=[client_user_id])


class UserSession(Base):
    """
    Model for user login sessions.
    """

    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, unique=True, index=True)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="login_sessions")


class Vote(Base):
    """
    Model for votes on posts.
    """

    __tablename__ = "votes"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )

    user = relationship("User", back_populates="votes")
    post = relationship("Post", back_populates="votes_rel")


class Report(Base):
    """
    Model for reporting inappropriate content.
    """

    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, nullable=False)
    report_reason = Column(String, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    reporter_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    status = Column(
        SQLAlchemyEnum(ReportStatus, name="report_status_enum"),
        default=ReportStatus.PENDING,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(String, nullable=True)
    is_valid = Column(Boolean, default=False)
    ai_detected = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)

    # التعديل هنا: تحديد عمود المفتاح الأجنبي بوضوح لعلاقة المستخدم الذي قام بالإبلاغ
    reporter = relationship(
        "User", foreign_keys=[reporter_id], back_populates="reports"
    )
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    post = relationship("Post", back_populates="reports")
    comment = relationship("Comment", back_populates="reports")


class Follow(Base):
    """
    Model for follow relationships between users.
    """

    __tablename__ = "follows"
    follower_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    is_mutual = Column(Boolean, default=False)

    follower = relationship(
        "User", back_populates="following", foreign_keys=[follower_id]
    )
    followed = relationship(
        "User", back_populates="followers", foreign_keys=[followed_id]
    )


class Message(Base):
    """
    Model for messages between users.
    """

    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_content = Column(LargeBinary, nullable=False)
    content = Column(Text, nullable=True)
    # Self-referential keys: add use_alter to break cycles.
    replied_to_id = Column(
        Integer,
        ForeignKey(
            "messages.id",
            ondelete="CASCADE",
            use_alter=True,
            name="fk_messages_replied_to_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    quoted_message_id = Column(
        Integer,
        ForeignKey(
            "messages.id",
            ondelete="CASCADE",
            use_alter=True,
            name="fk_messages_quoted_message_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    audio_url = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_current_location = Column(Boolean, default=False)
    location_name = Column(String, nullable=True)
    is_edited = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    message_type = Column(
        SQLAlchemyEnum(MessageType, name="message_type_enum"),
        nullable=False,
        default=MessageType.TEXT,
    )
    file_url = Column(String, nullable=True)
    conversation_id = Column(String, index=True)
    read_at = Column(TIMESTAMP(timezone=True), nullable=True)
    timestamp = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    link_preview = Column(JSON, nullable=True)
    language = Column(String, nullable=False, default="en")

    sender = relationship(
        "User", foreign_keys=[sender_id], back_populates="sent_messages"
    )
    receiver = relationship(
        "User", foreign_keys=[receiver_id], back_populates="received_messages"
    )
    replied_to = relationship(
        "Message", remote_side=[id], foreign_keys=[replied_to_id], backref="replies"
    )
    quoted_message = relationship(
        "Message", remote_side=[id], foreign_keys=[quoted_message_id], backref="quotes"
    )
    attachments = relationship(
        "MessageAttachment", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "idx_message_content",
            "content",
            postgresql_ops={"content": "gin_trgm_ops"},
            postgresql_using="gin",
        ),
        Index("idx_message_timestamp", "timestamp"),
    )


class EncryptedSession(Base):
    """
    Model for encrypted messaging sessions between users.
    """

    __tablename__ = "encrypted_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    other_user_id = Column(Integer, ForeignKey("users.id"))
    root_key = Column(LargeBinary)
    chain_key = Column(LargeBinary)
    next_header_key = Column(LargeBinary)
    ratchet_key = Column(LargeBinary)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship(
        "User", back_populates="encrypted_sessions", foreign_keys=[user_id]
    )
    other_user = relationship("User", foreign_keys=[other_user_id])


class EncryptedCall(Base):
    """
    Model for encrypted calls between users.
    """

    __tablename__ = "encrypted_calls"
    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    start_time = Column(DateTime, default=func.now())
    end_time = Column(DateTime, nullable=True)
    call_type = Column(Enum("audio", "video", name="call_type"))
    encryption_key = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    quality_score = Column(Integer, default=100)
    last_key_update = Column(DateTime, default=func.now())

    caller = relationship(
        "User", foreign_keys=[caller_id], back_populates="outgoing_encrypted_calls"
    )
    receiver = relationship(
        "User", foreign_keys=[receiver_id], back_populates="incoming_encrypted_calls"
    )


class Community(Base):
    """
    Model for communities/groups.
    """

    __tablename__ = "communities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    is_active = Column(Boolean, default=True)
    category_id = Column(Integer, ForeignKey("community_categories.id"), nullable=True)
    is_private = Column(Boolean, default=False)
    requires_approval = Column(Boolean, default=False)
    language = Column(String, nullable=False, default="en")

    category = relationship("CommunityCategory", back_populates="communities")
    owner = relationship("User", back_populates="owned_communities")
    members = relationship("CommunityMember", back_populates="community")
    posts = relationship(
        "Post", back_populates="community", cascade="all, delete-orphan"
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
    def member_count(self):
        return len(self.members)


class Category(Base):
    """
    Model for content categories (alternative grouping).
    """

    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)

    communities = relationship("Community", back_populates="category")


class SearchSuggestion(Base):
    """
    Model for search suggestions based on popular terms.
    """

    __tablename__ = "search_suggestions"
    id = Column(Integer, primary_key=True, index=True)
    term = Column(String, unique=True, index=True)
    frequency = Column(Integer, default=1)
    last_used = Column(DateTime, default=func.now(), onupdate=func.now())


class SearchStatistics(Base):
    """
    Model for tracking search queries.
    """

    __tablename__ = "search_statistics"
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True)
    count = Column(Integer, default=1)
    last_searched = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="search_history")


class Tag(Base):
    """
    Model for tags associated with communities.
    """

    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    communities = relationship(
        "Community", secondary=community_tags, back_populates="tags"
    )


class CommunityMember(Base):
    """
    Model for membership of users in communities.
    """

    __tablename__ = "community_members"
    __table_args__ = {"extend_existing": True}
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(
        SQLAlchemyEnum(CommunityRole, name="community_role_enum"),
        nullable=False,
        default=CommunityRole.MEMBER,
    )
    join_date = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    activity_score = Column(Integer, default=0)

    user = relationship("User", back_populates="community_memberships")
    community = relationship("Community", back_populates="members")


class CommunityStatistics(Base):
    """
    Model for daily statistics of a community.
    """

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
    """
    Model for rules governing a community.
    """

    __tablename__ = "community_rules"
    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )
    rule = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    community = relationship("Community", back_populates="rules")


class CommunityInvitation(Base):
    """
    Model for community invitations.
    """

    __tablename__ = "community_invitations"
    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="CASCADE"))
    inviter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    invitee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    community = relationship("Community", back_populates="invitations")
    inviter = relationship(
        "User", foreign_keys=[inviter_id], back_populates="sent_invitations"
    )
    invitee = relationship(
        "User", foreign_keys=[invitee_id], back_populates="received_invitations"
    )


class Reel(Base):
    """
    Model for reels (short videos).
    """

    __tablename__ = "reels"
    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    video_url = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )

    owner = relationship("User", back_populates="reels")
    community = relationship("Community", back_populates="reels")


class Article(Base):
    """
    Model for articles shared within communities.
    """

    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    author_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False
    )

    author = relationship("User", back_populates="articles")
    community = relationship("Community", back_populates="articles")


class Block(Base):
    """
    Model for user blocks.
    """

    __tablename__ = "blocks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    duration = Column(Integer, nullable=True)
    duration_unit = Column(Enum(BlockDuration), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    block_type = Column(Enum(BlockType), nullable=False, default=BlockType.FULL)

    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocks")
    blocked = relationship(
        "User", foreign_keys=[blocked_id], back_populates="blocked_by"
    )
    appeals = relationship("BlockAppeal", back_populates="block")


class BlockLog(Base):
    """
    Model for logging block actions.
    """

    __tablename__ = "block_logs"
    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    block_type = Column(Enum(BlockType), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    blocker = relationship(
        "User", foreign_keys=[blocker_id], back_populates="block_logs_given"
    )
    blocked = relationship(
        "User", foreign_keys=[blocked_id], back_populates="block_logs_received"
    )


class UserStatistics(Base):
    """
    Model for daily user statistics.
    """

    __tablename__ = "user_statistics"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    post_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)

    user = relationship("User", back_populates="statistics")


class SupportTicket(Base):
    """
    Model for support tickets submitted by users.
    """

    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        SQLAlchemyEnum(TicketStatus, name="ticket_status_enum"),
        default=TicketStatus.OPEN,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="support_tickets")
    responses = relationship(
        "TicketResponse", back_populates="ticket", cascade="all, delete-orphan"
    )


class TicketResponse(Base):
    """
    Model for responses to support tickets.
    """

    __tablename__ = "ticket_responses"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("SupportTicket", back_populates="responses")
    user = relationship("User")


class StickerPack(Base):
    """
    Model for sticker packs created by users.
    """

    __tablename__ = "sticker_packs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="sticker_packs")
    stickers = relationship("Sticker", back_populates="pack")


class Sticker(Base):
    """
    Model for individual stickers.
    """

    __tablename__ = "stickers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    image_url = Column(String)
    pack_id = Column(Integer, ForeignKey("sticker_packs.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved = Column(Boolean, default=False)

    pack = relationship("StickerPack", back_populates="stickers")
    categories = relationship(
        "StickerCategory", secondary=sticker_category_association, backref="stickers"
    )
    reports = relationship("StickerReport", back_populates="sticker")


class StickerCategory(Base):
    """
    Model for categories of stickers.
    """

    __tablename__ = "sticker_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)


class StickerReport(Base):
    """
    Model for reporting stickers.
    """

    __tablename__ = "sticker_reports"
    id = Column(Integer, primary_key=True, index=True)
    sticker_id = Column(Integer, ForeignKey("stickers.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sticker = relationship("Sticker", back_populates="reports")
    reporter = relationship("User")


class Call(Base):
    """
    Model for voice/video calls.
    """

    __tablename__ = "calls"
    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    call_type = Column(SQLAlchemyEnum(CallType, name="call_type_enum"))
    status = Column(
        SQLAlchemyEnum(CallStatus, name="call_status_enum"), default=CallStatus.PENDING
    )
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    encryption_key = Column(String, nullable=False)
    last_key_update = Column(DateTime(timezone=True), nullable=False)
    quality_score = Column(Integer, default=100)

    caller = relationship(
        "User", foreign_keys=[caller_id], back_populates="outgoing_calls"
    )
    receiver = relationship(
        "User", foreign_keys=[receiver_id], back_populates="incoming_calls"
    )
    screen_share_sessions = relationship("ScreenShareSession", back_populates="call")


class ScreenShareSession(Base):
    """
    Model for screen sharing sessions during calls.
    """

    __tablename__ = "screen_share_sessions"
    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"))
    sharer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        SQLAlchemyEnum(ScreenShareStatus, name="screen_share_status_enum"),
        default=ScreenShareStatus.ACTIVE,
    )
    error_message = Column(String, nullable=True)

    call = relationship("Call", back_populates="screen_share_sessions")
    sharer = relationship("User", back_populates="screen_shares")


class MessageAttachment(Base):
    """
    Model for attachments in messages.
    """

    __tablename__ = "message_attachments"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"))
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="attachments")


class ConversationStatistics(Base):
    """
    Model for statistics of conversations.
    """

    __tablename__ = "conversation_statistics"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    total_time = Column(Integer, default=0)  # in seconds
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())
    user1_id = Column(Integer, ForeignKey("users.id"))
    user2_id = Column(Integer, ForeignKey("users.id"))
    total_files = Column(Integer, default=0)
    total_emojis = Column(Integer, default=0)
    total_stickers = Column(Integer, default=0)
    total_response_time = Column(Float, default=0.0)
    total_responses = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)

    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])
