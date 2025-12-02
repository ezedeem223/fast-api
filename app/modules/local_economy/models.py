# app/modules/local_economy/models.py - Local economy domain models

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


class LocalMarketListing(Base):
    """Marketplace listing for hyper-local goods, services, or skills."""

    __tablename__ = "local_market_listings"

    id = Column(Integer, primary_key=True)

    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # "goods", "services", "skills"

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_radius_km = Column(Float, default=10.0)

    price = Column(Float, nullable=False)
    currency = Column(String, default="USD")

    views_count = Column(Integer, default=0)
    inquiries_count = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    seller = relationship("User")
    inquiries = relationship("LocalMarketInquiry", back_populates="listing")
    transactions = relationship("LocalMarketTransaction", back_populates="listing")


class LocalMarketInquiry(Base):
    """Buyer inquiry for a specific listing."""

    __tablename__ = "local_market_inquiries"

    id = Column(Integer, primary_key=True)

    listing_id = Column(
        Integer, ForeignKey("local_market_listings.id"), nullable=False, index=True
    )
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    message = Column(Text, nullable=False)

    status = Column(String, default="pending")  # "pending", "responded", "completed"

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    listing = relationship("LocalMarketListing", back_populates="inquiries")
    buyer = relationship("User")


class LocalMarketTransaction(Base):
    """Transaction created when a listing is purchased."""

    __tablename__ = "local_market_transactions"

    id = Column(Integer, primary_key=True)

    listing_id = Column(
        Integer, ForeignKey("local_market_listings.id"), nullable=False, index=True
    )
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    amount = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    listing = relationship("LocalMarketListing", back_populates="transactions")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])


class DigitalCooperative(Base):
    """Digital cooperatives for collective ownership and revenue sharing."""

    __tablename__ = "digital_cooperatives"

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=False)
    founder_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    total_shares = Column(Integer, nullable=False)

    members_count = Column(Integer, default=0)
    revenue = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    members = relationship("CooperativeMember", back_populates="cooperative")
    transactions = relationship("CooperativeTransaction", back_populates="cooperative")


class CooperativeMember(Base):
    """Membership record for a digital cooperative."""

    __tablename__ = "cooperative_members"

    id = Column(Integer, primary_key=True)

    cooperative_id = Column(
        Integer, ForeignKey("digital_cooperatives.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    shares_owned = Column(Integer, nullable=False)
    ownership_percentage = Column(Float, nullable=False)

    joined_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    cooperative = relationship("DigitalCooperative", back_populates="members")
    user = relationship("User")


class CooperativeTransaction(Base):
    """Revenue distribution events for a cooperative."""

    __tablename__ = "cooperative_transactions"

    id = Column(Integer, primary_key=True)
    cooperative_id = Column(
        Integer, ForeignKey("digital_cooperatives.id"), nullable=False, index=True
    )
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    cooperative = relationship("DigitalCooperative", back_populates="transactions")


__all__ = [
    "LocalMarketListing",
    "LocalMarketInquiry",
    "LocalMarketTransaction",
    "DigitalCooperative",
    "CooperativeMember",
    "CooperativeTransaction",
]
