# ruff: noqa: F401,F403
"""
File: schemas.py
Description: This module defines Pydantic schemas for the social media project.
It covers various domains including reactions, votes, posts, comments, notifications,
users, communities, search, and more. The file is organized into sections with clear
English comments to enhance readability and maintainability.

Note:
- Canonical schemas now live under `app.modules.*.schemas`; this file re-exports for
  backwards compatibility. Prefer importing from the module-specific paths for new code.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# ================================================================
# Imports
# ================================================================
from pydantic import BaseModel, ConfigDict, EmailStr, Field, conint

from app.modules.community.schemas import *  # noqa: F401,F403
from app.modules.community.schemas import (
    Category,
)
from app.modules.community.schemas import CommunityCreate as CommunityCreateBase
from app.modules.community.schemas import (
    CommunityInvitationOut,
    CommunityMemberOut,
)
from app.modules.community.schemas import CommunityOut as CommunityOutBase
from app.modules.community.schemas import (
    CommunityOutRef,
    CommunityRuleCreate,
    CommunityRuleOut,
)
from app.modules.messaging import MessageType
from app.modules.messaging.schemas import *  # noqa: F401,F403
from app.modules.messaging.schemas import Message
from app.modules.moderation.schemas import *  # noqa: F401,F403
from app.modules.moderation.schemas import (
    BanReasonOut,
    BanStatisticsOverview,
    BanTypeDistribution,
    EffectivenessTrend,
)
from app.modules.notifications.schemas import *  # noqa: F401,F403
from app.modules.notifications.schemas import (
    NotificationAnalytics,
    NotificationBase,
    NotificationCreate,
    NotificationDeliveryLogOut,
    NotificationDeliveryStatus,
    NotificationFeedResponse,
    NotificationGroupOut,
    NotificationOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
    NotificationStatistics,
    NotificationSummary,
    NotificationUpdate,
    NotificationWithLogs,
    PushNotification,
)
from app.modules.posts.schemas import *  # noqa: F401,F403
from app.modules.posts.schemas import (
    Comment,
    CommentOut,
    Post,
    PostCategory,
    PostCategoryCreate,
    PostOut,
)
from app.modules.search.schemas import *  # noqa: F401,F403
from app.modules.stickers.schemas import *  # noqa: F401,F403
from app.modules.support.schemas import *  # noqa: F401,F403
from app.modules.users.schemas import *  # noqa: F401,F403
from app.modules.users.schemas import UserContentOut, UserOut, UserRoleUpdate

# ================================================================
# Reactions and Vote Models
# Re-exported from app.modules.posts.schemas for backwards compatibility.
# ================================================================


# ================================================================
# User Email and Security Questions Schemas
# Schemas related to email changes and security questions settings.
# ================================================================


# ================================================================
# Following and User Listing Schemas
# Schemas to represent following lists and user-related information.
# ================================================================

# ================================================================
# Post Vote and Analytics Models
# Re-exported from app.modules.posts.schemas for backwards compatibility.
# ================================================================


# ================================================================
# Hashtag Models
# Re-exported from app.modules.posts.schemas for backwards compatibility.
# ================================================================


# ================================================================
# Search and Sorting Models
# Re-exported from app.modules.search.schemas for backwards compatibility.
# ================================================================
# ================================================================
# Screen Share and Appeal Models
# Schemas related to screen sharing sessions and appeal processes.
# ================================================================
class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ================================================================
# Ban, Block, and Appeal Models
# Re-exported from app.modules.moderation.schemas.
# ================================================================
# Business registration model
class BusinessRegistration(BaseModel):
    business_name: str
    business_registration_number: str
    bank_account_info: str


# Follow statistics model
class FollowStatistics(BaseModel):
    followers_count: int
    following_count: int
    daily_growth: Dict[date, int]
    interaction_rate: float


# Copyright types for posts
class CopyrightType(str, Enum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


# ================================================================
# Business and Comment Statistics Models
# Schemas for business verification and comment statistics.
# ================================================================
class BusinessVerificationUpdate(BaseModel):
    id_document: Any  # Expected to be an UploadFile (from fastapi)
    passport: Any
    business_document: Any
    selfie: Any


class BusinessUserOut(BaseModel):
    business_name: str
    business_registration_number: str
    verification_status: VerificationStatus
    is_verified_business: bool

    model_config = ConfigDict(from_attributes=True)


class BusinessTransactionCreate(BaseModel):
    client_user_id: int
    amount: float


class BusinessTransactionOut(BaseModel):
    id: int
    business_user: "UserOut"
    client_user: "UserOut"
    amount: float
    commission: float
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Privacy and User Profile Models
# Schemas for updating user privacy settings and profiles.
# ================================================================


# ================================================================
# Search and Ticket Models
# Search schemas are provided by app.modules.search.schemas.
# Support ticket schemas are provided by app.modules.support.schemas.
# ================================================================


# Models for encrypted calls (voice/video)
class EncryptedCallCreate(BaseModel):
    receiver_id: int
    call_type: str


class EncryptedCallUpdate(BaseModel):
    quality_score: Optional[int] = None
    is_active: Optional[bool] = None


class EncryptedCallOut(BaseModel):
    id: int
    caller_id: int
    receiver_id: int
    start_time: datetime
    call_type: str
    is_active: bool
    quality_score: int

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Article, Community, and Reel Models (Content Models)
# Schemas for articles, communities, and reels content.
# ================================================================
class ArticleBase(BaseModel):
    title: str
    content: str


# Extend community create schema locally to keep legacy rule payload support.
class CommunityCreate(CommunityCreateBase):
    rules: Optional[List["CommunityRuleCreate"]] = Field(default_factory=list)


class CommunityOut(CommunityOutBase):
    category: Optional["Category"] = None


class ReelBase(BaseModel):
    title: str
    video_url: str
    description: Optional[str] = None


# UI and Notification Settings


# Repost statistics model
class RepostStatisticsOut(BaseModel):
    post_id: int
    repost_count: int
    last_reposted: datetime

    model_config = ConfigDict(from_attributes=True)


# Settings for reposting posts
class RepostSettings(BaseModel):
    scope: str = "public"
    community_id: Optional[int] = None
    visibility: Optional[str] = "all_members"
    custom_message: Optional[str] = None


# Model for creating reposts (extends PostCreate later)
class RepostCreate(BaseModel):
    repost_settings: Optional[RepostSettings] = None


# Preferences for notification updates
# Amenhotep (chatbot or analytics) models
class AmenhotepMessageCreate(BaseModel):
    message: str


class AmenhotepMessageOut(BaseModel):
    id: int
    user_id: int
    message: str
    response: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AmenhotepAnalyticsBase(BaseModel):
    session_id: str
    total_messages: int
    topics_discussed: List[str]
    session_duration: int
    satisfaction_score: Optional[float]


class AmenhotepAnalyticsCreate(AmenhotepAnalyticsBase):
    user_id: int


class AmenhotepAnalyticsOut(AmenhotepAnalyticsBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AmenhotepSessionSummary(BaseModel):
    total_sessions: int
    average_duration: float
    most_discussed_topics: List[str]
    average_satisfaction: float


class TopPostStat(BaseModel):
    id: int
    title: Optional[str] = None
    votes: int
    comment_count: int

    model_config = ConfigDict(from_attributes=True)


class TopUserStat(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    followers: int
    post_count: int
    comment_count: int

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Social Media and Account Models
# Schemas for social account integration and social posts.
# ================================================================
class SocialMediaType(str, Enum):
    REDDIT = "reddit"
    LINKEDIN = "linkedin"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


# Base model for a social account
class SocialAccountBase(BaseModel):
    platform: SocialMediaType
    account_username: Optional[str] = None


class SocialAccountCreate(SocialAccountBase):
    pass


class SocialAccountOut(SocialAccountBase):
    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# User settings models

# ================================================================
# Warning and Ban Models for Users
# Re-exported from app.modules.moderation.schemas.
# ================================================================


# ================================================================
# User Models
# Schemas for user creation, update, and output.
# ================================================================


class InitialKeyExchange(BaseModel):
    user_id: int
    public_key: str


class KeyExchange(BaseModel):
    public_key: str


class DecryptedMessage(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    timestamp: datetime
    message_type: MessageType
    is_read: bool
    read_at: Optional[datetime]
    conversation_id: str


class SessionKeyUpdate(BaseModel):
    session_id: int
    new_public_key: str


# ================================================================
# Token Models
# Schemas for handling JWT tokens.
# ================================================================
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[int] = None


# ================================================================
# Vote Models
# Schemas for voting on posts.
# ================================================================
class Vote(BaseModel):
    post_id: int
    dir: conint(le=1)


class VoterOut(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class VotersListOut(BaseModel):
    voters: List[VoterOut]
    total_count: int


# ================================================================
# Community Models
# Schemas for community creation, update, and details.
# ================================================================
#
# All community domain schemas are re-exported from app.modules.community.schemas.
#
class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str


# Post category schemas live in app.modules.posts.schemas.
PostCategorySchema = PostCategory


# ================================================================
# Community Analytics Models
# Schemas for analyzing community performance and engagement.
# ================================================================
#
# See app.modules.community.schemas for analytics-specific schemas.
#


class EncryptedSessionCreate(BaseModel):
    other_user_id: int


class EncryptedSessionOut(BaseModel):
    id: int
    user_id: int
    other_user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EncryptedSessionUpdate(BaseModel):
    root_key: str
    chain_key: str
    next_header_key: str
    ratchet_key: str


# ================================================================
# Post Models
# Schemas for creating, updating, and representing posts.
# ================================================================
# Poll schemas are imported from app.modules.posts.schemas.


# ================================================================
# Comment Models
# Schemas for creating, editing, and representing comments.
# ================================================================
# ================================================================
# Message Models
# Schemas for message creation, update, and conversation details are
# re-exported from app.modules.messaging.schemas for compatibility.
# ================================================================


# ================================================================
# Article Models
# Schemas for creating and representing articles.
# ================================================================
class ArticleCreate(ArticleBase):
    community_id: int


class Article(ArticleBase):
    id: int
    created_at: datetime
    author_id: int
    community_id: int
    author: UserOut

    model_config = ConfigDict(from_attributes=True)


class ArticleOut(Article):
    community: CommunityOutRef

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Reel Models
# Schemas for creating and representing reels.
# ================================================================
class ReelCreate(ReelBase):
    community_id: int
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class Reel(ReelBase):
    id: int
    created_at: datetime
    owner_id: int
    community_id: int
    expires_at: datetime
    is_active: bool
    view_count: int
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)


class ReelOut(Reel):
    community: CommunityOutRef

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Community Invitation Models
# Schemas for handling community invitations.
# ================================================================
# ================================================================
# 2FA Models
# Schemas for two-factor authentication processes.
# ================================================================
class Enable2FAResponse(BaseModel):
    otp_secret: str


class Verify2FARequest(BaseModel):
    otp: str


class Verify2FAResponse(BaseModel):
    message: str


# ================================================================
# Additional User Session and Authentication Models
# Schemas for managing user sessions and authentication tokens.
# ================================================================


# ================================================================
# Sticker Models
# Re-exported from app.modules.stickers.schemas.
# ================================================================


# ================================================================
# Resolve Forward References
# This section ensures that forward references are updated.
# ================================================================
Message.model_rebuild()
CommunityOut.model_rebuild(
    _types_namespace={
        "CommunityMemberOut": CommunityMemberOut,
        "CommunityRuleOut": CommunityRuleOut,
    }
)
ArticleOut.model_rebuild()
ReelOut.model_rebuild()
Post.model_rebuild()
PostOut.model_rebuild()
Comment.model_rebuild()
CommunityInvitationOut.model_rebuild()
UserContentOut.model_rebuild(
    _types_namespace={
        "PostComment": Comment,
        "PostOut": PostOut,
        "ArticleOut": ArticleOut,
        "ReelOut": ReelOut,
    }
)
