"""Sticker domain models and association tables."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default

sticker_category_association = Table(
    "sticker_category_association",
    Base.metadata,
    Column(
        "sticker_id",
        Integer,
        ForeignKey("stickers.id", ondelete="CASCADE"),
    ),
    Column(
        "category_id",
        Integer,
        ForeignKey("sticker_categories.id", ondelete="CASCADE"),
    ),
)


class StickerPack(Base):
    """User-created sticker packs."""

    __tablename__ = "sticker_packs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    creator = relationship("User", back_populates="sticker_packs")
    stickers = relationship("Sticker", back_populates="pack")


class Sticker(Base):
    """Individual sticker entry."""

    __tablename__ = "stickers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    image_url = Column(String)
    pack_id = Column(Integer, ForeignKey("sticker_packs.id"))
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    approved = Column(Boolean, default=False)

    pack = relationship("StickerPack", back_populates="stickers")
    categories = relationship(
        "StickerCategory", secondary=sticker_category_association, backref="stickers"
    )
    reports = relationship("StickerReport", back_populates="sticker")
    comments = relationship("Comment", back_populates="sticker")


class StickerCategory(Base):
    """Categories used to organise stickers."""

    __tablename__ = "sticker_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)


class StickerReport(Base):
    """Reports filed against stickers."""

    __tablename__ = "sticker_reports"

    id = Column(Integer, primary_key=True, index=True)
    sticker_id = Column(Integer, ForeignKey("stickers.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    sticker = relationship("Sticker", back_populates="reports")
    reporter = relationship("User")


__all__ = [
    "sticker_category_association",
    "StickerPack",
    "Sticker",
    "StickerCategory",
    "StickerReport",
]
