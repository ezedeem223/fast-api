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
class UserType(enum.Enum):
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


class ScreenShareStatus(enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


# Определение моделей
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    phone_number = Column(String)
    is_verified = Column(Boolean, default=False)
    verification_document = Column(String, nullable=True)
    otp_secret = Column(String, nullable=True)
    is_2fa_enabled = Column(Boolean, default=False)
    role = Column(Enum(UserRole), default=UserRole.USER)
    profile_image = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    website = Column(String, nullable=True)
    joined_at = Column(DateTime, server_default=func.now())
    privacy_level = Column(Enum(PrivacyLevel), default=PrivacyLevel.PUBLIC)
    custom_privacy = Column(JSON, default={})
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)
    skills = Column(ARRAY(String), nullable=True)
    interests = Column(ARRAY(String), nullable=True)
    ui_settings = Column(JSONB, default={})
    notifications_settings = Column(JSONB, default={})
    user_type = Column(Enum(UserType), default=UserType.PERSONAL)
    business_name = Column(String, nullable=True)
    business_registration_number = Column(String, nullable=True)
    bank_account_info = Column(String, nullable=True)
    id_document_url = Column(String, nullable=True)
    passport_url = Column(String, nullable=True)
    business_document_url = Column(String, nullable=True)
    selfie_url = Column(String, nullable=True)
    hide_read_status = Column(Boolean, default=False)
    verification_status = Column(
        Enum(VerificationStatus), default=VerificationStatus.PENDING
    )
    is_verified_business = Column(Boolean, default=False)
    hashed_password = Column(String, nullable=False)
    public_key = Column(LargeBinary)

    # Relationships будут добавлены позже


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
    is_safe_content = Column(Boolean, default=True)
    is_short_video = Column(Boolean, default=False)

    __table_args__ = (Index("idx_title_user", "title", "owner_id"),)

    # Relationships будут добавлены позже


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
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships будут добавлены позже


class BusinessTransaction(Base):
    __tablename__ = "business_transactions"

    id = Column(Integer, primary_key=True, index=True)
    business_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships будут добавлены позже


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

    # Relationships будут добавлены позже


class Vote(Base):
    __tablename__ = "votes"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )


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
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(String, nullable=True)

    # Relationships будут добавлены позже


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

    # Relationships будут добавлены позже


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
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.TEXT)
    file_url = Column(String, nullable=True)
    conversation_id = Column(String, index=True)
    read_at = Column(TIMESTAMP(timezone=True), nullable=True)
    timestamp = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    link_preview = Column(JSON, nullable=True)

    __table_args__ = (
        Index(
            "idx_message_content",
            "content",
            postgresql_ops={"content": "gin_trgm_ops"},
            postgresql_using="gin",
        ),
        Index("idx_message_timestamp", "timestamp"),
    )

    # Relationships будут добавлены позже


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

    # user = relationship("User", foreign_keys=[user_id], back_populates="encrypted_sessions")
    # other_user = relationship("User", foreign_keys=[other_user_id])
    # encrypted_sessions = relationship(
    #     "EncryptedSession", foreign_keys=[EncryptedSession.user_id], back_populates="user"
    # )


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

    # Relationships будут добавлены позже

    @property
    def member_count(self):
        return len(self.members)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)

    # Relationships будут добавлены позже


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    # Relationships будут добавлены позже


class CommunityMember(Base):
    __tablename__ = "community_members"
    __table_args__ = {"extend_existing": True}

    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(Enum(CommunityRole), nullable=False, default=CommunityRole.MEMBER)
    join_date = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    activity_score = Column(Integer, default=0)

    # Relationships будут добавлены позже


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

    __table_args__ = (
        UniqueConstraint("community_id", "date", name="uix_community_date"),
    )

    # Relationships будут добавлены позже


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

    # Relationships будут добавлены позже


class CommunityInvitation(Base):
    __tablename__ = "community_invitations"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="CASCADE"))
    inviter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    invitee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships будут добавлены позже


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

    # Relationships будут добавлены позже


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


class Block(Base):
    __tablename__ = "blocks"
    blocker_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships будут добавлены позже


class UserStatistics(Base):
    __tablename__ = "user_statistics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    post_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)

    # Relationships будут добавлены позже


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.OPEN)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships будут добавлены позже


class TicketResponse(Base):
    __tablename__ = "ticket_responses"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships будут добавлены позже


class StickerPack(Base):
    __tablename__ = "sticker_packs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships будут добавлены позже


class Sticker(Base):
    __tablename__ = "stickers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    image_url = Column(String)
    pack_id = Column(Integer, ForeignKey("sticker_packs.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved = Column(Boolean, default=False)

    # Relationships будут добавлены позже


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

    # Relationships будут добавлены позже


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    call_type = Column(Enum(CallType))
    status = Column(Enum(CallStatus), default=CallStatus.PENDING)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

    # Relationships будут добавлены позже


class ScreenShareSession(Base):
    __tablename__ = "screen_share_sessions"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"))
    sharer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(ScreenShareStatus), default=ScreenShareStatus.ACTIVE)
    error_message = Column(String, nullable=True)


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
    total_time = Column(Integer, default=0)  # في الثواني
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


# Теперь добавим отношения
User.posts = relationship("Post", back_populates="owner", cascade="all, delete-orphan")
User.comments = relationship(
    "Comment", back_populates="owner", cascade="all, delete-orphan"
)
User.reports = relationship(
    "Report", back_populates="reporter", cascade="all, delete-orphan"
)
User.follows = relationship(
    "Follow",
    foreign_keys=[Follow.follower_id],
    back_populates="follower",
    cascade="all, delete-orphan",
)
User.followed_by = relationship(
    "Follow",
    foreign_keys=[Follow.followed_id],
    back_populates="followed",
    cascade="all, delete-orphan",
)
User.sent_messages = relationship(
    "Message",
    foreign_keys=[Message.sender_id],
    back_populates="sender",
    cascade="all, delete-orphan",
)
User.received_messages = relationship(
    "Message",
    foreign_keys=[Message.receiver_id],
    back_populates="receiver",
    cascade="all, delete-orphan",
)
User.owned_communities = relationship(
    "Community", back_populates="owner", cascade="all, delete-orphan"
)
User.community_memberships = relationship(
    "CommunityMember", back_populates="user", cascade="all, delete-orphan"
)
User.blocks = relationship(
    "Block",
    foreign_keys=[Block.blocker_id],
    back_populates="blocker",
    cascade="all, delete-orphan",
)
User.blocked_by = relationship(
    "Block",
    foreign_keys=[Block.blocked_id],
    back_populates="blocked",
    cascade="all, delete-orphan",
)
User.reels = relationship("Reel", back_populates="owner", cascade="all, delete-orphan")
User.articles = relationship(
    "Article", back_populates="author", cascade="all, delete-orphan"
)
User.sent_invitations = relationship(
    "CommunityInvitation",
    foreign_keys=[CommunityInvitation.inviter_id],
    back_populates="inviter",
)
User.received_invitations = relationship(
    "CommunityInvitation",
    foreign_keys=[CommunityInvitation.invitee_id],
    back_populates="invitee",
)
User.login_sessions = relationship(
    "UserSession", back_populates="user", cascade="all, delete-orphan"
)
User.statistics = relationship("UserStatistics", back_populates="user")
User.support_tickets = relationship("SupportTicket", back_populates="user")
User.sticker_packs = relationship("StickerPack", back_populates="creator")
User.outgoing_calls = relationship(
    "Call", foreign_keys=[Call.caller_id], back_populates="caller"
)
User.incoming_calls = relationship(
    "Call", foreign_keys=[Call.receiver_id], back_populates="receiver"
)
User.screen_shares = relationship("ScreenShareSession", back_populates="sharer")


Post.owner = relationship("User", back_populates="posts")
Post.comments = relationship(
    "Comment", back_populates="post", cascade="all, delete-orphan"
)
Post.community = relationship("Community", back_populates="posts")
Post.reports = relationship(
    "Report", back_populates="post", cascade="all, delete-orphan"
)

Comment.owner = relationship("User", back_populates="comments")
Comment.post = relationship("Post", back_populates="comments")
Comment.reports = relationship(
    "Report", back_populates="comment", cascade="all, delete-orphan"
)

BusinessTransaction.business_user = relationship(
    "User", foreign_keys=[BusinessTransaction.business_user_id]
)
BusinessTransaction.client_user = relationship(
    "User", foreign_keys=[BusinessTransaction.client_user_id]
)

UserSession.user = relationship("User", back_populates="login_sessions")

Report.reporter = relationship(
    "User", foreign_keys=[Report.reporter_id], back_populates="reports"
)
Report.reviewer = relationship("User", foreign_keys=[Report.reviewed_by])
Report.post = relationship("Post", back_populates="reports")
Report.comment = relationship("Comment", back_populates="reports")

Follow.follower = relationship(
    "User", foreign_keys=[Follow.follower_id], back_populates="follows"
)
Follow.followed = relationship(
    "User", foreign_keys=[Follow.followed_id], back_populates="followed_by"
)

Message.sender = relationship(
    "User", foreign_keys=[Message.sender_id], back_populates="sent_messages"
)
Message.receiver = relationship(
    "User", foreign_keys=[Message.receiver_id], back_populates="received_messages"
)
Message.replied_to = relationship(
    "Message",
    remote_side=[Message.id],
    foreign_keys=[Message.replied_to_id],
    backref="replies",
)
Message.quoted_message = relationship(
    "Message",
    remote_side=[Message.id],
    foreign_keys=[Message.quoted_message_id],
    backref="quotes",
)
attachments = relationship(
    "MessageAttachment", back_populates="message", cascade="all, delete-orphan"
)
Community.owner = relationship("User", back_populates="owned_communities")
Community.members = relationship("CommunityMember", back_populates="community")
Community.posts = relationship(
    "Post", back_populates="community", cascade="all, delete-orphan"
)
Community.reels = relationship(
    "Reel", back_populates="community", cascade="all, delete-orphan"
)
Community.articles = relationship(
    "Article", back_populates="community", cascade="all, delete-orphan"
)
Community.invitations = relationship(
    "CommunityInvitation", back_populates="community", cascade="all, delete-orphan"
)
Community.rules = relationship(
    "CommunityRule", back_populates="community", cascade="all, delete-orphan"
)
Community.statistics = relationship(
    "CommunityStatistics", back_populates="community", cascade="all, delete-orphan"
)
Community.category = relationship("Category", back_populates="communities")
Community.tags = relationship(
    "Tag", secondary=community_tags, back_populates="communities"
)

Category.communities = relationship("Community", back_populates="category")

Tag.communities = relationship(
    "Community", secondary=community_tags, back_populates="tags"
)

CommunityMember.user = relationship("User", back_populates="community_memberships")
CommunityMember.community = relationship("Community", back_populates="members")

CommunityStatistics.community = relationship("Community", back_populates="statistics")

CommunityRule.community = relationship("Community", back_populates="rules")

CommunityInvitation.community = relationship("Community", back_populates="invitations")
CommunityInvitation.inviter = relationship(
    "User",
    foreign_keys=[CommunityInvitation.inviter_id],
    back_populates="sent_invitations",
)
CommunityInvitation.invitee = relationship(
    "User",
    foreign_keys=[CommunityInvitation.invitee_id],
    back_populates="received_invitations",
)

Reel.owner = relationship("User", back_populates="reels")
Reel.community = relationship("Community", back_populates="reels")

Article.author = relationship("User", back_populates="articles")
Article.community = relationship("Community", back_populates="articles")

Block.blocker = relationship(
    "User", foreign_keys=[Block.blocker_id], back_populates="blocks"
)
Block.blocked = relationship(
    "User", foreign_keys=[Block.blocked_id], back_populates="blocked_by"
)

UserStatistics.user = relationship("User", back_populates="statistics")

SupportTicket.user = relationship("User", back_populates="support_tickets")
SupportTicket.responses = relationship(
    "TicketResponse", back_populates="ticket", cascade="all, delete-orphan"
)

TicketResponse.ticket = relationship("SupportTicket", back_populates="responses")
TicketResponse.user = relationship("User")

StickerPack.creator = relationship("User", back_populates="sticker_packs")
StickerPack.stickers = relationship("Sticker", back_populates="pack")

Sticker.pack = relationship("StickerPack", back_populates="stickers")
Sticker.categories = relationship(
    "StickerCategory", secondary=sticker_category_association, backref="stickers"
)
Sticker.reports = relationship("StickerReport", back_populates="sticker")

StickerReport.sticker = relationship("Sticker", back_populates="reports")
StickerReport.reporter = relationship("User")
sharer = relationship("User", back_populates="screen_shares")


Call.caller = relationship(
    "User", foreign_keys=[Call.caller_id], back_populates="outgoing_calls"
)
Call.receiver = relationship(
    "User", foreign_keys=[Call.receiver_id], back_populates="incoming_calls"
)
call = relationship("Call", back_populates="screen_share_sessions")
Call.screen_share_sessions = relationship("ScreenShareSession", back_populates="call")


# user = relationship("User", foreign_keys=[user_id], back_populates="encrypted_sessions")
# other_user = relationship("User", foreign_keys=[other_user_id])
# encrypted_sessions = relationship(
#     "EncryptedSession", foreign_keys=[EncryptedSession.user_id], back_populates="user"
# )
