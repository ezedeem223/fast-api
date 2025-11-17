"""Pydantic schemas for the moderation domain (blocks, bans, reports)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr, model_validator

from app.modules.moderation.models import (
    AppealStatus,
    BlockDuration,
    BlockType as BlockTypeEnum,
)
from app.modules.messaging.schemas import ScreenShareSessionOut


class WordSeverity(str, Enum):
    warn = "warn"
    ban = "ban"


class BannedWordBase(BaseModel):
    word: str
    severity: WordSeverity = WordSeverity.warn


class BannedWordCreate(BannedWordBase):
    pass


class BannedWordUpdate(BaseModel):
    word: Optional[str] = None
    severity: Optional[WordSeverity] = None


class BannedWordOut(BannedWordBase):
    id: int
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BlockAppealCreate(BaseModel):
    block_id: int
    reason: str


class BlockAppealOut(BaseModel):
    id: int
    block_id: int
    user_id: int
    reason: str
    status: AppealStatus
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewer_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class BlockAppealReview(BaseModel):
    status: AppealStatus


class BlockStatistics(BaseModel):
    total_blocks: int
    active_blocks: int
    expired_blocks: int

    model_config = ConfigDict(from_attributes=True)


class IPBanBase(BaseModel):
    ip_address: str
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


class IPBanCreate(IPBanBase):
    pass


class IPBanOut(IPBanBase):
    id: int
    banned_at: datetime
    created_by: int

    model_config = ConfigDict(from_attributes=True)


class CallType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"


class CallStatus(str, Enum):
    PENDING = "pending"
    ONGOING = "ongoing"
    ENDED = "ended"


class CallCreate(BaseModel):
    receiver_id: int
    call_type: CallType


class CallUpdate(BaseModel):
    status: CallStatus
    current_screen_share_id: Optional[int] = None


class CallOut(BaseModel):
    id: int
    caller_id: int
    receiver_id: int
    call_type: CallType
    status: CallStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    current_screen_share: Optional["ScreenShareSessionOut"] = None
    quality_score: int

    model_config = ConfigDict(from_attributes=True)


class BlockCreate(BaseModel):
    blocked_id: int
    duration: Optional[int] = Field(None, ge=1)
    duration_unit: Optional[BlockDuration] = None
    block_type: BlockTypeEnum = BlockTypeEnum.FULL


class BlockSettings(BaseModel):
    default_block_type: BlockTypeEnum


class BlockOut(BaseModel):
    blocker_id: int
    blocked_id: int
    created_at: datetime
    ends_at: Optional[datetime] = None
    block_type: BlockTypeEnum

    model_config = ConfigDict(from_attributes=True)


class BlockLogCreate(BaseModel):
    blocked_id: int
    block_type: BlockTypeEnum
    reason: Optional[str] = None


class BlockLogOut(BaseModel):
    id: int
    blocker_id: int
    blocked_id: int
    block_type: BlockTypeEnum
    reason: Optional[str]
    created_at: datetime
    ended_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BanStatisticsOverview(BaseModel):
    total_bans: int
    ip_bans: int
    word_bans: int
    user_bans: int
    average_effectiveness: float


class BanReasonOut(BaseModel):
    reason: str
    count: int
    last_used: datetime

    model_config = ConfigDict(from_attributes=True)


class EffectivenessTrend(BaseModel):
    date: date
    effectiveness: float


class BanTypeDistribution(BaseModel):
    ip_bans: int
    word_bans: int
    user_bans: int


class BlockedUserOut(BaseModel):
    id: int
    username: str
    email: str
    block_type: BlockTypeEnum
    reason: Optional[str]
    blocked_since: datetime

    model_config = ConfigDict(from_attributes=True)


class WarningCreate(BaseModel):
    reason: str


class BanCreate(BaseModel):
    reason: str


class ReportStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class ReportBase(BaseModel):
    reason: constr(min_length=1)
    report_reason: Optional[str] = None
    ai_detected: bool = False
    ai_confidence: Optional[float] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @model_validator(mode="after")
    def _sync_report_reason(self):
        sanitized = self.reason.strip()
        if not sanitized:
            raise ValueError("Report reason cannot be empty")
        self.reason = sanitized
        if not self.report_reason:
            self.report_reason = sanitized
        return self


class ReportCreate(ReportBase):
    post_id: Optional[int] = None
    comment_id: Optional[int] = None

    @model_validator(mode="after")
    def _validate_target(self):
        has_post = self.post_id is not None
        has_comment = self.comment_id is not None
        if has_post == has_comment:
            raise ValueError("Provide either post_id or comment_id to submit a report")
        return self


class Report(ReportBase):
    id: int
    post_id: Optional[int]
    comment_id: Optional[int]
    reported_user_id: Optional[int]
    reporter_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportReview(BaseModel):
    is_valid: bool


class ReportUpdate(BaseModel):
    status: ReportStatus
    resolution_notes: Optional[str] = None


class ReportOut(Report):
    status: ReportStatus
    reviewed_by: Optional[int]
    resolution_notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "AppealStatus",
    "BanCreate",
    "BanReasonOut",
    "BanStatisticsOverview",
    "BanTypeDistribution",
    "BannedWordBase",
    "BannedWordCreate",
    "BannedWordOut",
    "BannedWordUpdate",
    "BlockAppealCreate",
    "BlockAppealOut",
    "BlockAppealReview",
    "BlockCreate",
    "BlockLogCreate",
    "BlockLogOut",
    "BlockOut",
    "BlockSettings",
    "BlockStatistics",
    "BlockTypeEnum",
    "BlockedUserOut",
    "CallCreate",
    "CallOut",
    "CallStatus",
    "CallType",
    "CallUpdate",
    "EffectivenessTrend",
    "IPBanBase",
    "IPBanCreate",
    "IPBanOut",
    "Report",
    "ReportBase",
    "ReportCreate",
    "ReportOut",
    "ReportReview",
    "ReportStatus",
    "ReportUpdate",
    "WarningCreate",
    "WordSeverity",
]
