"""Messaging domain Pydantic schemas.

Covers messages, attachments, conversations/members, calls/screen shares, and encrypted sessions.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.messaging import (
    ConversationMemberRole,
    ConversationType,
    MessageType,
    ScreenShareStatus,
)


class MessageAttachmentBase(BaseModel):
    """Pydantic schema for MessageAttachmentBase."""
    file_url: str
    file_type: str


class MessageAttachmentCreate(MessageAttachmentBase):
    """Pydantic schema for MessageAttachmentCreate."""
    pass


class MessageAttachment(MessageAttachmentBase):
    """Pydantic schema for MessageAttachment."""
    id: int
    message_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    """Pydantic schema for MessageBase."""
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
    """Pydantic schema for MessageCreate."""
    receiver_id: Optional[int] = Field(default=None, alias="recipient_id")
    conversation_id: Optional[str] = None
    attachments: List[MessageAttachmentCreate] = Field(default_factory=list)
    sticker_id: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class LinkPreview(BaseModel):
    """Pydantic schema for LinkPreview."""
    title: str
    description: Optional[str] = None
    image: Optional[str] = None
    url: str


class Message(MessageBase):
    """Pydantic schema for Message."""
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
    """Pydantic schema for SortOrder."""
    ASC = "asc"
    DESC = "desc"


class MessageSearch(BaseModel):
    """Pydantic schema for MessageSearch."""
    query: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    message_type: Optional[MessageType] = None
    conversation_id: Optional[str] = None
    sort_order: SortOrder = SortOrder.DESC
    skip: int = 0
    limit: int = 100


class MessageSearchResponse(BaseModel):
    """Pydantic schema for MessageSearchResponse."""
    total: int
    messages: List[Message]


class MessageUpdate(BaseModel):
    """Pydantic schema for MessageUpdate."""
    content: str


class MessageOut(BaseModel):
    """Pydantic schema for MessageOut."""
    message: Message
    count: int

    model_config = ConfigDict(from_attributes=True)


class ConversationMemberOut(BaseModel):
    """Pydantic schema for ConversationMemberOut."""
    user_id: int
    role: ConversationMemberRole
    joined_at: datetime
    is_muted: bool
    notifications_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class ConversationBase(BaseModel):
    """Pydantic schema for ConversationBase."""
    title: Optional[str] = None


class ConversationCreate(ConversationBase):
    """Pydantic schema for ConversationCreate."""
    member_ids: List[int] = Field(default_factory=list)


class ConversationOut(ConversationBase):
    """Pydantic schema for ConversationOut."""
    id: str
    type: ConversationType
    created_by: Optional[int]
    created_at: datetime
    last_message_at: Optional[datetime]
    members: List[ConversationMemberOut]

    model_config = ConfigDict(from_attributes=True)


class ConversationMembersUpdate(BaseModel):
    """Pydantic schema for ConversationMembersUpdate."""
    member_ids: List[int]


class ConversationStatisticsBase(BaseModel):
    """Pydantic schema for ConversationStatisticsBase."""
    total_messages: int
    total_time: int
    last_message_at: datetime


class ConversationStatisticsCreate(ConversationStatisticsBase):
    """Pydantic schema for ConversationStatisticsCreate."""
    conversation_id: str
    user1_id: int
    user2_id: int


class ConversationStatistics(ConversationStatisticsBase):
    """Pydantic schema for ConversationStatistics."""
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
    """Pydantic schema for ScreenShareStart."""
    call_id: int


class ScreenShareEnd(BaseModel):
    """Pydantic schema for ScreenShareEnd."""
    session_id: int


class ScreenShareUpdate(BaseModel):
    """Pydantic schema for ScreenShareUpdate."""
    status: ScreenShareStatus
    error_message: Optional[str] = None


class ScreenShareSessionOut(BaseModel):
    """Pydantic schema for ScreenShareSessionOut."""
    id: int
    call_id: int
    sharer_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: ScreenShareStatus
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)
