"""Pydantic schemas for the stickers domain."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class StickerPackBase(BaseModel):
    """Pydantic schema for StickerPackBase."""
    name: str


class StickerPackCreate(StickerPackBase):
    """Pydantic schema for StickerPackCreate."""
    pass


class StickerPack(StickerPackBase):
    """Pydantic schema for StickerPack."""
    id: int
    creator_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StickerBase(BaseModel):
    """Pydantic schema for StickerBase."""
    name: str
    image_url: str


class StickerCreate(StickerBase):
    """Pydantic schema for StickerCreate."""
    pack_id: int
    category_ids: List[int]


class Sticker(BaseModel):
    """Pydantic schema for Sticker."""
    id: int
    name: str
    image_url: str
    pack_id: int
    created_at: datetime
    approved: bool
    categories: List["StickerCategory"]

    model_config = ConfigDict(from_attributes=True)


class StickerPackWithStickers(StickerPack):
    """Pydantic schema for StickerPackWithStickers."""
    stickers: List[Sticker]


class StickerCategoryBase(BaseModel):
    """Pydantic schema for StickerCategoryBase."""
    name: str


class StickerCategoryCreate(StickerCategoryBase):
    """Pydantic schema for StickerCategoryCreate."""
    pass


class StickerCategory(StickerCategoryBase):
    """Pydantic schema for StickerCategory."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class StickerReportBase(BaseModel):
    """Pydantic schema for StickerReportBase."""
    sticker_id: int
    reason: str


class StickerReportCreate(StickerReportBase):
    """Pydantic schema for StickerReportCreate."""
    pass


class StickerReport(StickerReportBase):
    """Pydantic schema for StickerReport."""
    id: int
    reporter_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "Sticker",
    "StickerBase",
    "StickerCategory",
    "StickerCategoryBase",
    "StickerCategoryCreate",
    "StickerCreate",
    "StickerPack",
    "StickerPackBase",
    "StickerPackCreate",
    "StickerPackWithStickers",
    "StickerReport",
    "StickerReportBase",
    "StickerReportCreate",
]
