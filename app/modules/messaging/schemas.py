"""Messaging domain Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.messaging import (
    MessageType,
    ScreenShareStatus,
    ConversationType,
    ConversationMemberRole,
)


class MessageAttachmentBase(BaseModel):
    file_url: str
    file_type: str


class MessageAttachmentCreate(MessageAttachmentBase):
    pass


class MessageAttachment(MessageAttachmentBase):
    id: int
    message_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    content: Optional[str] = None
    encrypted_content: Optional[str] = None
    message_type: MessageType = MessageType.TEXT
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_current_location: Optional[bool] = False
    location_name: Optional[str] = None
    replied_to_id: Optional[int] = None
    quoted_message_id: Optional[int] = None
    is_read: bool = False
    read_at: Optional[datetime] = None
    file_url: Optional[str] = None


class MessageCreate(MessageBase):
    receiver_id: Optional[int] = Field(default=None, alias="recipient_id")
    conversation_id: Optional[str] = None
    attachments: List[MessageAttachmentCreate] = Field(default_factory=list)
    sticker_id: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class LinkPreview(BaseModel):
    title: str
    description: Optional[str] = None
    image: Optional[str] = None
    url: str


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: Optional[int] = None
    conversation_id: str
    created_at: datetime
    timestamp: datetime
    sticker_id: Optional[int] = None
    has_emoji: bool = False
    has_sticker: bool = False
    has_audio: bool = False
    has_file: bool = False
    link_preview: Optional[LinkPreview] = None

    model_config = ConfigDict(from_attributes=True)


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class MessageSearch(BaseModel):
    query: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    message_type: Optional[MessageType] = None
    conversation_id: Optional[str] = None
    sort_order: SortOrder = SortOrder.DESC
    skip: int = 0
    limit: int = 100


class MessageSearchResponse(BaseModel):
    total: int
    messages: List[Message]


class MessageUpdate(BaseModel):
    content: str


class MessageOut(BaseModel):
    message: Message
    count: int

    model_config = ConfigDict(from_attributes=True)


class ConversationMemberOut(BaseModel):
    user_id: int
    role: ConversationMemberRole
    joined_at: datetime
    is_muted: bool
    notifications_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class ConversationBase(BaseModel):
    title: Optional[str] = None


class ConversationCreate(ConversationBase):
    member_ids: List[int] = Field(default_factory=list)


class ConversationOut(ConversationBase):
    id: str
    type: ConversationType
    created_by: Optional[int]
    created_at: datetime
    last_message_at: Optional[datetime]
    members: List[ConversationMemberOut]

    model_config = ConfigDict(from_attributes=True)


class ConversationMembersUpdate(BaseModel):
    member_ids: List[int]


class ConversationStatisticsBase(BaseModel):
    total_messages: int
    total_time: int
    last_message_at: datetime


class ConversationStatisticsCreate(ConversationStatisticsBase):
    conversation_id: str
    user1_id: int
    user2_id: int


class ConversationStatistics(ConversationStatisticsBase):
    id: int
    conversation_id: str
    user1_id: int
    user2_id: int
    total_files: int
    total_emojis: int
    total_stickers: int
    average_response_time: float

    model_config = ConfigDict(from_attributes=True)


class ScreenShareStart(BaseModel):
    call_id: int


class ScreenShareEnd(BaseModel):
    session_id: int


class ScreenShareUpdate(BaseModel):
    status: ScreenShareStatus
    error_message: Optional[str] = None


class ScreenShareSessionOut(BaseModel):
    id: int
    call_id: int
    sharer_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: ScreenShareStatus
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)
