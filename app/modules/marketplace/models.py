"""SQLAlchemy models for the marketplace domain."""
# app/modules/marketplace/models.py - Creator marketplace models

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ContentListing(Base):
    """Digital content listing (courses, templates, guides, assets)."""

    __tablename__ = "content_listings"

    id = Column(Integer, primary_key=True)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    content_type = Column(String, nullable=False)  # "course", "template", etc.

    price = Column(Float, nullable=False)
    currency = Column(String, default="USD")

    sales_count = Column(Integer, default=0)
    rating = Column(Float, default=0.0)
    reviews_count = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    creator = relationship("User")
    purchases = relationship("ContentPurchase", back_populates="listing")
    reviews = relationship("ContentReview", back_populates="listing")


class ContentPurchase(Base):
    """Purchase record for a content listing."""

    __tablename__ = "content_purchases"

    id = Column(Integer, primary_key=True)

    listing_id = Column(
        Integer, ForeignKey("content_listings.id"), nullable=False, index=True
    )
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    amount = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    creator_earnings = Column(Float, nullable=False)

    purchased_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    listing = relationship("ContentListing", back_populates="purchases")
    buyer = relationship("User")


class ContentSubscription(Base):
    """Recurring subscription to a creator's premium feed."""

    __tablename__ = "content_subscriptions"

    id = Column(Integer, primary_key=True)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subscriber_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    monthly_price = Column(Float, nullable=False)

    is_active = Column(Boolean, default=True)

    started_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    ends_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[creator_id])
    subscriber = relationship("User", foreign_keys=[subscriber_id])


class ContentReview(Base):
    """Lightweight review entity to capture feedback and ratings."""

    __tablename__ = "content_reviews"

    id = Column(Integer, primary_key=True)
    listing_id = Column(
        Integer, ForeignKey("content_listings.id"), nullable=False, index=True
    )
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Float, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    listing = relationship("ContentListing", back_populates="reviews")
    reviewer = relationship("User")


__all__ = [
    "ContentListing",
    "ContentPurchase",
    "ContentSubscription",
    "ContentReview",
]
