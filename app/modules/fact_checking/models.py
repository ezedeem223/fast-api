# app/modules/fact_checking/models.py

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class FactCheckStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    PARTIALLY_TRUE = "partially_true"
    FALSE = "false"
    MISLEADING = "misleading"
    UNVERIFIABLE = "unverifiable"


class Fact(Base):
    """Submitted fact/claim awaiting verification."""

    __tablename__ = "facts"

    id = Column(Integer, primary_key=True)
    claim = Column(Text, nullable=False)
    source_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    source_comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    submitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    status = Column(Enum(FactCheckStatus), default=FactCheckStatus.PENDING, index=True)
    verification_score = Column(Float, default=0.0)
    community_consensus = Column(Float, default=0.0)

    description = Column(Text, nullable=True)
    evidence_links = Column(JSON, default=[])
    sources = Column(JSON, default=[])

    verification_count = Column(Integer, default=0)
    support_votes = Column(Integer, default=0)
    oppose_votes = Column(Integer, default=0)

    created_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)

    submitter = relationship("User")
    verifications = relationship(
        "FactVerification", back_populates="fact", cascade="all, delete-orphan"
    )
    corrections = relationship(
        "FactCorrection", back_populates="fact", cascade="all, delete-orphan"
    )
    credibility_badges = relationship(
        "CredibilityBadge", back_populates="fact", cascade="all, delete-orphan"
    )
    votes = relationship(
        "FactVote", back_populates="fact", cascade="all, delete-orphan"
    )


class FactVerification(Base):
    """Verifier verdict for a fact."""

    __tablename__ = "fact_verifications"

    id = Column(Integer, primary_key=True)
    fact_id = Column(Integer, ForeignKey("facts.id"), nullable=False, index=True)
    verifier_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    verdict = Column(Enum(FactCheckStatus), nullable=False)
    confidence_score = Column(Float, default=0.5)
    explanation = Column(Text, nullable=True)
    evidence_provided = Column(JSON, default=[])

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    fact = relationship("Fact", back_populates="verifications")
    verifier = relationship("User")


class FactCorrection(Base):
    """Correction proposal for a fact."""

    __tablename__ = "fact_corrections"

    id = Column(Integer, primary_key=True)
    fact_id = Column(Integer, ForeignKey("facts.id"), nullable=False, index=True)
    corrector_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_claim = Column(Text, nullable=False)
    corrected_claim = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    fact = relationship("Fact", back_populates="corrections")
    corrector = relationship("User")


class CredibilityBadge(Base):
    """Badges issued to highlight verified facts."""

    __tablename__ = "credibility_badges"

    id = Column(Integer, primary_key=True)
    fact_id = Column(Integer, ForeignKey("facts.id"), nullable=False, index=True)
    badge_type = Column(String, nullable=False)
    issuer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    issued_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    fact = relationship("Fact", back_populates="credibility_badges")
    issuer = relationship("User")


class FactVote(Base):
    """Community votes on a fact's credibility."""

    __tablename__ = "fact_votes"

    id = Column(Integer, primary_key=True)
    fact_id = Column(Integer, ForeignKey("facts.id"), nullable=False, index=True)
    voter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vote_type = Column(String, nullable=False)  # "support" or "oppose"
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    fact = relationship("Fact", back_populates="votes")
    voter = relationship("User")


class MisinformationWarning(Base):
    """Warnings attached to posts or comments flagged for misinformation."""

    __tablename__ = "misinformation_warnings"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True, index=True)
    warning_type = Column(String, nullable=False)
    related_fact_id = Column(Integer, ForeignKey("facts.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    related_fact = relationship("Fact")


__all__ = [
    "FactCheckStatus",
    "Fact",
    "FactVerification",
    "FactCorrection",
    "CredibilityBadge",
    "FactVote",
    "MisinformationWarning",
]
