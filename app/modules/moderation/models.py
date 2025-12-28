"""Moderation domain enums and models (blocks, bans, and related logs)."""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Date,
    Float,
    Interval,
    ForeignKey,
    Enum,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default


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


class UserWarning(Base):
    """Track warnings issued to users."""

    __tablename__ = "user_warnings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())


class UserBan(Base):
    """Store ban records for specific users."""

    __tablename__ = "user_bans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    duration = Column(Interval, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())


class IPBan(Base):
    """Persist IP-level bans."""

    __tablename__ = "ip_bans"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, index=True, nullable=False)
    reason = Column(String)
    banned_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    created_by_user = relationship("User", back_populates="ip_bans_created")


class BannedWord(Base):
    """Words/phrases blocked by moderation."""

    __tablename__ = "banned_words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True, nullable=False)
    severity = Column(Enum("warn", "ban", name="word_severity"), default="warn")
    is_regex = Column(Boolean, default=False, server_default="0")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    created_by_user = relationship("User", back_populates="banned_words_created")


class BanStatistics(Base):
    """Aggregate moderation stats per day."""

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
    """Counts usage of various ban reasons."""

    __tablename__ = "ban_reasons"

    id = Column(Integer, primary_key=True, index=True)
    reason = Column(String, nullable=False)
    count = Column(Integer, default=1)
    last_used = Column(DateTime(timezone=True), server_default=timestamp_default())


class Block(Base):
    """Represents a block between two users."""

    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=timestamp_default()
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
    """History audit for block actions."""

    __tablename__ = "block_logs"

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    block_type = Column(Enum(BlockType), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    blocker = relationship(
        "User", foreign_keys=[blocker_id], back_populates="block_logs_given"
    )
    blocked = relationship(
        "User", foreign_keys=[blocked_id], back_populates="block_logs_received"
    )


class BlockAppeal(Base):
    """Appeal submitted for an active block."""

    __tablename__ = "block_appeals"

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    reason = Column(String, nullable=False)
    status = Column(Enum(AppealStatus), default=AppealStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    block = relationship("Block", back_populates="appeals")
    user = relationship("User", foreign_keys=[user_id], back_populates="block_appeals")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class AuditLog(Base):
    """Audit trail for admin actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=True)
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    admin = relationship("User")


__all__ = [
    "BlockDuration",
    "BlockType",
    "AppealStatus",
    "UserWarning",
    "UserBan",
    "IPBan",
    "BannedWord",
    "BanStatistics",
    "BanReason",
    "Block",
    "BlockLog",
    "BlockAppeal",
]
