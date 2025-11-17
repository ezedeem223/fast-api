"""Pydantic schemas for the stickers domain."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class StickerPackBase(BaseModel):
    name: str


class StickerPackCreate(StickerPackBase):
    pass


class StickerPack(StickerPackBase):
    id: int
    creator_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StickerBase(BaseModel):
    name: str
    image_url: str


class StickerCreate(StickerBase):
    pack_id: int
    category_ids: List[int]


class Sticker(BaseModel):
    id: int
    name: str
    image_url: str
    pack_id: int
    created_at: datetime
    approved: bool
    categories: List["StickerCategory"]

    model_config = ConfigDict(from_attributes=True)


class StickerPackWithStickers(StickerPack):
    stickers: List[Sticker]


class StickerCategoryBase(BaseModel):
    name: str


class StickerCategoryCreate(StickerCategoryBase):
    pass


class StickerCategory(StickerCategoryBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class StickerReportBase(BaseModel):
    sticker_id: int
    reason: str


class StickerReportCreate(StickerReportBase):
    pass


class StickerReport(StickerReportBase):
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
