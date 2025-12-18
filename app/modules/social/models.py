"""Social/interactions domain models."""

from __future__ import annotations

import enum

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Float,
    JSON,
    Text,
)
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship, synonym

from app.core.database import Base
from app.core.db_defaults import timestamp_default
from app.modules.users.associations import user_hashtag_follows
from app.modules.posts import post_hashtags


class ReportStatus(str, enum.Enum):
    """Lifecycle for abuse reports."""

    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class Hashtag(Base):
    """Simple hashtag entity used across posts."""

    __tablename__ = "hashtags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    followers = relationship(
        "User",
        secondary=user_hashtag_follows,
        back_populates="followed_hashtags",
    )
    posts = relationship(
        "Post",
        secondary=post_hashtags,
        back_populates="hashtags",
    )


class BusinessTransaction(Base):
    """Represents a business engagement between two users."""

    __tablename__ = "business_transactions"

    id = Column(Integer, primary_key=True, index=True)
    business_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    client_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    business_user = relationship("User", foreign_keys=[business_user_id])
    client_user = relationship("User", foreign_keys=[client_user_id])


class Vote(Base):
    """Simple up/down vote bridge between users and posts."""

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
    """Content moderation reports covering posts or comments."""

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
    reported_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    status = Column(
        SAEnum(ReportStatus, name="report_status_enum"),
        default=ReportStatus.PENDING,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(String, nullable=True)
    is_valid = Column(Boolean, default=False)
    ai_detected = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)

    reporter = relationship(
        "User", foreign_keys=[reporter_id], back_populates="reports"
    )
    reported_user = relationship(
        "User", foreign_keys=[reported_user_id], back_populates="reports_received"
    )
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    post = relationship("Post", back_populates="reports")
    comment = relationship("Comment", back_populates="reports")
    # Backwards compatible attribute expected throughout the legacy codebase/tests.
    reason = synonym("report_reason")


class Follow(Base):
    """Follower/following relationships between users."""

    __tablename__ = "follows"

    follower_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=timestamp_default()
    )
    is_mutual = Column(Boolean, default=False)

    follower = relationship(
        "User", back_populates="following", foreign_keys=[follower_id]
    )
    followed = relationship(
        "User", back_populates="followers", foreign_keys=[followed_id]
    )




class ExpertiseBadge(Base):

    __tablename__ = "expertise_badges"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    category = Column(
        String, nullable=False
    )  # "programming", "design", "writing", etc.
    level = Column(Integer, default=1)

    posts_count = Column(Integer, default=0)
    engagement_score = Column(Float, default=0.0)
    community_votes = Column(Integer, default=0)

    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    earned_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    user = relationship("User", foreign_keys=[user_id])
    verifier = relationship("User", foreign_keys=[verified_by])


# ==========================================
# ==========================================
class ImpactCertificate(Base):
    """
    Verifiable certificate of social impact issued to a user.
    """

    __tablename__ = "impact_certificates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String, nullable=False)
    description = Column(String)

    # Stores metrics like {"trees_planted": 50, "people_helped": 100}
    impact_metrics = Column(JSON, default={})

    issued_at = Column(TIMESTAMP(timezone=True), server_default=timestamp_default())
    issuer_authority = Column(String, nullable=True, default="System")

    user = relationship("User", backref="impact_certificates")


# ==========================================
# ==========================================
class CulturalDictionaryEntry(Base):
    """
    Crowdsourced dictionary for cultural terms and idioms.
    """

    __tablename__ = "cultural_dictionary"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String, nullable=False, index=True)
    definition = Column(Text, nullable=False)
    cultural_context = Column(
        Text, nullable=False, doc="Explanation of usage, origin, and nuance"
    )
    language = Column(String, nullable=False, default="ar")

    submitted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    is_verified = Column(Boolean, default=False)

    submitter = relationship("User", foreign_keys=[submitted_by])


__all__ = [
    "ReportStatus",
    "Hashtag",
    "BusinessTransaction",
    "Vote",
    "Report",
    "Follow",
    "ExpertiseBadge",
    "ImpactCertificate",
    "CulturalDictionaryEntry",
]
