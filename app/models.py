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
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql import func
from .database import Base
import enum
from datetime import date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import TSVECTOR

Base = declarative_base()


post_mentions = Table(
    "post_mentions",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)
# Определение таблиц ассоциаций
community_tags = Table(
    "community_tags",
    Base.metadata,
    Column("community_id", Integer, ForeignKey("communities.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

sticker_category_association = Table(
    "sticker_category_association",
    Base.metadata,
    Column("sticker_id", Integer, ForeignKey("stickers.id")),
    Column("category_id", Integer, ForeignKey("sticker_categories.id")),
)


# Определение Enum классов
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


class BlockAppeal(Base):
    __tablename__ = "block_appeals"

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    status = Column(Enum(AppealStatus), default=AppealStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    block = relationship("Block", back_populates="appeals")
    user = relationship("User", foreign_keys=[user_id], back_populates="block_appeals")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class Hashtag(Base):
    __tablename__ = "hashtags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)


# إضافة جدول وسيط لربط المستخدمين بالهاشتاغات التي يتابعونها
user_hashtag_follows = Table(
    "user_hashtag_follows",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("hashtag_id", Integer, ForeignKey("hashtags.id")),
)


class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    reaction_type = Column(Enum(ReactionType), nullable=False)

    user = relationship("User", back_populates="reactions")
    post = relationship("Post", back_populates="reactions")
    comment = relationship("Comment", back_populates="reactions")

    __table_args__ = (
        Index("ix_reactions_user_id", user_id),
        Index("ix_reactions_post_id", post_id),
        Index("ix_reactions_comment_id", comment_id),
    )


# Определение моделей
class User(Base):
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
    preferred_language = Column(String, default=ar)
    auto_translate = Column(Boolean, default=True)
    suspension_end_date = Column(DateTime, nullable=True)
    language = Column(String, nullable=False, default="en")

    token_blacklist = relationship("TokenBlacklist", back_populates="user")
    posts = relationship("Post", back_populates="owner", cascade="all, delete-orphan")
    comments = relationship(
        "Comment", back_populates="owner", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="reporter", cascade="all, delete-orphan"
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
    encrypted_sessions = relationship("EncryptedSession", back_populates="user")
    votes = relationship("Vote", back_populates="user")
    followed_hashtags = relationship(
        "Hashtag", secondary=user_hashtag_follows, back_populates="followers"
    )
    reactions = relationship(
        "Reaction", back_populates="user", cascade="all, delete-orphan"
    )
    block_logs_given = relationship(
        "BlockLog", foreign_keys=[BlockLog.blocker_id], back_populates="blocker"
    )
    block_logs_received = relationship(
        "BlockLog", foreign_keys=[BlockLog.blocked_id], back_populates="blocked"
    )
    block_appeals = relationship(
        "BlockAppeal", foreign_keys=[BlockAppeal.user_id], back_populates="user"
    )
    mentions = relationship(
        "Post", secondary=post_mentions, back_populates="mentioned_users"
    )
    outgoing_encrypted_calls = relationship(
        "EncryptedCall", foreign_keys=[EncryptedCall.caller_id], back_populates="caller"
    )
    incoming_encrypted_calls = relationship(
        "EncryptedCall",
        foreign_keys=[EncryptedCall.receiver_id],
        back_populates="receiver",
    )
    search_history = relationship("SearchStatistics", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class UserActivity(Base):
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    activity_type = Column(String)
    timestamp = Column(DateTime, default=func.now())
    details = Column(JSON)

    user = relationship("User", back_populates="activities")


User.activities = relationship("UserActivity", back_populates="user")


class CommunityCategory(Base):
    __tablename__ = "community_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)


class UserEvent(Base):
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    event_type = Column(
        String, nullable=False
    )  # e.g., "login", "post", "comment", "report"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="events")


User.events = relationship("UserEvent", back_populates="user")


class UserWarning(Base):
    __tablename__ = "user_warnings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserBan(Base):
    __tablename__ = "user_bans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    duration = Column(Interval, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IPBan(Base):
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
    __tablename__ = "banned_words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True, nullable=False)
    severity = Column(Enum("warn", "ban", name="word_severity"), default="warn")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by_user = relationship("User", back_populates="banned_words_created")


User.banned_words_created = relationship("BannedWord", back_populates="created_by_user")


class BanStatistics(Base):
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
    __tablename__ = "ban_reasons"

    id = Column(Integer, primary_key=True, index=True)
    reason = Column(String, nullable=False)
    count = Column(Integer, default=1)
    last_used = Column(DateTime(timezone=True), server_default=func.now())


class Post(Base):
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
    category_id = Column(Integer, ForeignKey("post_categories.id"))
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    is_published = Column(Boolean, default=False)
    original_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
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
    is_flagged: Column = Column(Boolean, default=False)
    flag_reason: Column = Column(String, nullable=True)
    search_vector = Column(TSVECTOR)
    __table_args__ = (
        Index("idx_post_search_vector", search_vector, postgresql_using="gin"),
    )
    share_scope = Column(String, default="public")  # public, community, group
    shared_with_community_id = Column(
        Integer, ForeignKey("communities.id"), nullable=True
    )
    score = Column(Float, default=0.0, index=True)

    sharing_settings = Column(JSONB, default={})  # لتخزين إعدادات المشاركة المتقدمة
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
    votes = relationship("Vote", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_title_user", "title", "owner_id"),)
    hashtags = relationship("Hashtag", secondary="post_hashtags")
    post_hashtags = Table(
        "post_hashtags",
        Base.metadata,
        Column("post_id", Integer, ForeignKey("posts.id")),
        Column("hashtag_id", Integer, ForeignKey("hashtags.id")),
    )
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


User.notification_preferences = relationship(
    "NotificationPreferences", back_populates="user", uselist=False
)


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


class NotificationPreferences(Base):
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
    )  # realtime, hourly, daily, weekly
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="notification_preferences")


class NotificationGroup(Base):
    __tablename__ = "notification_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_type = Column(String, nullable=False)  # e.g., "comment_thread", "post_likes"
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    count = Column(Integer, default=1)
    sample_notification_id = Column(Integer, ForeignKey("notifications.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("Notification", back_populates="group")


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    blacklisted_on = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))


class PostVoteStatistics(Base):
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
    __tablename__ = "poll_options"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_text = Column(String, nullable=False)
    post = relationship("Post", back_populates="poll_options")
    votes = relationship("PollVote", back_populates="option")


class Poll(Base):
    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), unique=True)
    end_date = Column(DateTime)
    post = relationship("Post", back_populates="poll")


class PollVote(Base):
    __tablename__ = "poll_votes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    option_id = Column(Integer, ForeignKey("poll_options.id"))
    user = relationship("User", back_populates="poll_votes")
    post = relationship("Post")
    option = relationship("PollOption", back_populates="votes")


class CopyrightType(str, PyEnum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


class Notification(Base):
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
    metadata = Column(JSONB, default={})
    group_id = Column(Integer, ForeignKey("notification_groups.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="notifications")
    group = relationship("NotificationGroup", back_populates="notifications")


User.notifications = relationship("Notification", back_populates="user")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, nullable=False)
    content = Column(String, nullable=False)
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
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


class PostCategory(Base):
    __tablename__ = "post_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    parent_id = Column(Integer, ForeignKey("post_categories.id"))
    is_active = Column(Boolean, default=True)

    children = relationship(
        "PostCategory", back_populates="parent", cascade="all, delete-orphan"
    )
    parent = relationship("PostCategory", back_populates="children", remote_side=[id])
    posts = relationship("Post", back_populates="category")


class CommentEditHistory(Base):
    __tablename__ = "comment_edit_history"

    id = Column(Integer, primary_key=True, nullable=False)
    comment_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    previous_content = Column(String, nullable=False)
    edited_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    comment = relationship("Comment", back_populates="edit_history")

    # Добавление индекса для улучшения производительности
    __table_args__ = (Index("ix_comment_edit_history_comment_id", "comment_id"),)


class BusinessTransaction(Base):
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
    __tablename__ = "votes"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )

    user = relationship("User", back_populates="votes")
    post = relationship("Post", back_populates="votes")


class Report(Base):
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
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(String, nullable=True)

    reporter = relationship(
        "User", foreign_keys=[reporter_id], back_populates="reports"
    )
    is_valid = Column(Boolean, default=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    ai_detected: Column = Column(Boolean, default=False)
    ai_confidence: Column = Column(Float, nullable=True)

    reviewer = relationship("User", foreign_keys=[reviewed_by])
    post = relationship("Post", back_populates="reports")
    comment = relationship("Comment", back_populates="reports")


class Follow(Base):
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
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_content = Column(LargeBinary, nullable=False)
    content = Column(Text, nullable=True)
    replied_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    quoted_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
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
    __tablename__ = "communities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    is_active = Column(Boolean, default=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    category_id = Column(Integer, ForeignKey("community_categories.id"))
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
    category = relationship("Category", back_populates="communities")
    tags = relationship("Tag", secondary=community_tags, back_populates="communities")

    @property
    def member_count(self):
        return len(self.members)


CommunityCategory.communities = relationship("Community", back_populates="category")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)

    communities = relationship("Community", back_populates="category")


class SearchSuggestion(Base):
    __tablename__ = "search_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String, unique=True, index=True)
    frequency = Column(Integer, default=1)
    last_used = Column(DateTime, default=func.now(), onupdate=func.now())


class SearchStatistics(Base):
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
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    communities = relationship(
        "Community", secondary=community_tags, back_populates="tags"
    )


class CommunityMember(Base):
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
    __tablename__ = "blocks"
    blocker_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    duration = Column(Integer, nullable=True)
    duration_unit = Column(Enum(BlockDuration), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocks")
    blocked = relationship(
        "User", foreign_keys=[blocked_id], back_populates="blocked_by"
    )
    block_type = Column(Enum(BlockType), nullable=False, default=BlockType.FULL)
    appeals = relationship("BlockAppeal", back_populates="block")


class BlockLog(Base):
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
    __tablename__ = "ticket_responses"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("SupportTicket", back_populates="responses")
    user = relationship("User")


class StickerPack(Base):
    __tablename__ = "sticker_packs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="sticker_packs")
    stickers = relationship("Sticker", back_populates="pack")


class Sticker(Base):
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
    __tablename__ = "sticker_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)


class StickerReport(Base):
    __tablename__ = "sticker_reports"

    id = Column(Integer, primary_key=True, index=True)
    sticker_id = Column(Integer, ForeignKey("stickers.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sticker = relationship("Sticker", back_populates="reports")
    reporter = relationship("User")


class Call(Base):
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
    __tablename__ = "message_attachments"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"))
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="attachments")


class ConversationStatistics(Base):
    __tablename__ = "conversation_statistics"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    total_time = Column(Integer, default=0)  # в секундах
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
