"""SQLAlchemy models and enums for the messaging domain.

Includes conversations/members, messages/attachments, encrypted sessions, calls/screen shares,
and conversation statistics used by analytics. Enums describe call/message types and roles.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql.sqltypes import TIMESTAMP

from app.core.database import Base
from app.core.db_defaults import timestamp_default


def _conversation_id_default(context):
    """Generate a reproducible conversation id when one is not supplied."""
    params = context.get_current_parameters()
    sender = params.get("sender_id")
    receiver = params.get("receiver_id")
    if sender is None or receiver is None:
        return None
    user_a, user_b = sorted((sender, receiver))
    return f"{user_a}-{user_b}"


def _utcnow():
    """Return timezone-aware UTC timestamps for python-side defaults."""
    return datetime.now(timezone.utc)


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


class ConversationType(str, enum.Enum):
    DIRECT = "direct"
    GROUP = "group"


class ConversationMemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Conversation(Base):
    """Conversation container representing direct or group chats."""

    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String, nullable=True)
    type = Column(
        SAEnum(ConversationType, name="conversation_type_enum"),
        default=ConversationType.DIRECT,
    )
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    messages = relationship("Message", back_populates="conversation")
    members = relationship(
        "ConversationMember",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ConversationMember(Base):
    """Membership of users inside conversations."""

    __tablename__ = "conversation_members"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    role = Column(
        SAEnum(ConversationMemberRole, name="conversation_member_role"),
        default=ConversationMemberRole.MEMBER,
    )
    joined_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    is_muted = Column(Boolean, default=False)
    notifications_enabled = Column(Boolean, default=True)

    conversation = relationship("Conversation", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        Index(
            "ix_conversation_members_unique", "conversation_id", "user_id", unique=True
        ),
    )


class Message(Base):
    """Message exchanged between users."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    encrypted_content = Column(LargeBinary, nullable=True, default=b"")
    content = Column(Text, nullable=True)
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
        SAEnum(MessageType, name="message_type_enum"),
        nullable=False,
        default=MessageType.TEXT,
    )
    file_url = Column(String, nullable=True)
    conversation_id = Column(
        String,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        default=_conversation_id_default,
    )
    read_at = Column(TIMESTAMP(timezone=True), nullable=True)
    timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=timestamp_default(),
    )
    link_preview = Column(JSON, nullable=True)
    language = Column(String, nullable=False, default="en")
    has_emoji = Column(Boolean, default=False)

    # Backwards compatibility alias for legacy code that expected a `created_at` column.
    created_at = synonym("timestamp")

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
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index(
            "idx_message_content",
            "content",
            postgresql_ops={"content": "gin_trgm_ops"},
            postgresql_using="gin",
        ),
        Index("idx_message_timestamp", "timestamp"),
    )


class MessageAttachment(Base):
    """Attachment metadata linked to a message."""

    __tablename__ = "message_attachments"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"))
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    message = relationship("Message", back_populates="attachments")


class EncryptedSession(Base):
    """Double Ratchet session state for secure messaging."""

    __tablename__ = "encrypted_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    other_user_id = Column(Integer, ForeignKey("users.id"))
    root_key = Column(LargeBinary)
    chain_key = Column(LargeBinary)
    next_header_key = Column(LargeBinary)
    ratchet_key = Column(LargeBinary)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())

    user = relationship(
        "User", back_populates="encrypted_sessions", foreign_keys=[user_id]
    )
    other_user = relationship("User", foreign_keys=[other_user_id])


class EncryptedCall(Base):
    """History of encrypted calls between users."""

    __tablename__ = "encrypted_calls"

    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    start_time = Column(DateTime, default=timestamp_default())
    end_time = Column(DateTime, nullable=True)
    call_type = Column(SAEnum(CallType, name="call_type"))
    encryption_key = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    quality_score = Column(Integer, default=100)
    last_key_update = Column(DateTime, default=timestamp_default())

    caller = relationship(
        "User", foreign_keys=[caller_id], back_populates="outgoing_encrypted_calls"
    )
    receiver = relationship(
        "User", foreign_keys=[receiver_id], back_populates="incoming_encrypted_calls"
    )


class Call(Base):
    """Voice/video calls between users."""

    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    call_type = Column(SAEnum(CallType, name="call_type_enum"))
    status = Column(
        SAEnum(CallStatus, name="call_status_enum"), default=CallStatus.PENDING
    )
    start_time = Column(DateTime(timezone=True), server_default=timestamp_default())
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
    """Screen sharing sessions during calls."""

    __tablename__ = "screen_share_sessions"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"))
    sharer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    start_time = Column(DateTime(timezone=True), server_default=timestamp_default())
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        SAEnum(ScreenShareStatus, name="screen_share_status_enum"),
        default=ScreenShareStatus.ACTIVE,
    )
    error_message = Column(String, nullable=True)

    call = relationship("Call", back_populates="screen_share_sessions")
    sharer = relationship("User", back_populates="screen_shares")


class ConversationStatistics(Base):
    """Aggregate metrics for a conversation."""

    __tablename__ = "conversation_statistics"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    total_time = Column(Integer, default=0)
    last_message_at = Column(
        DateTime(timezone=True), server_default=timestamp_default()
    )
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
