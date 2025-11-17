"""
File: schemas.py
Description: This module defines Pydantic schemas for the social media project.
It covers various domains including reactions, votes, posts, comments, notifications,
users, communities, search, and more. The file is organized into sections with clear
English comments to enhance readability and maintainability.
"""

from __future__ import annotations

# ================================================================
# Imports
# ================================================================
from pydantic import (
    BaseModel,
    EmailStr,
    conint,
    ValidationError,
    ConfigDict,
    constr,
    HttpUrl,
    Field,
    model_validator,
)
from datetime import datetime, date, timedelta, time
from typing import Optional, List, Dict, Tuple, Union, Any
from enum import Enum
from app.modules.notifications.schemas import (
    NotificationPreferencesUpdate,
    NotificationPreferencesOut,
    NotificationBase,
    NotificationCreate,
    NotificationUpdate,
    NotificationDeliveryStatus,
    NotificationStatistics,
    NotificationAnalytics,
    NotificationGroupOut,
    NotificationDeliveryLogOut,
    NotificationWithLogs,
    NotificationOut,
)
from app.modules.posts import ReactionType
from app.modules.posts.schemas import (
    Comment,
    CommentBase,
    CommentCreate,
    CommentEditHistoryOut,
    CommentOut,
    CommentStatistics,
    CommentUpdate,
    FlagCommentRequest,
    PostCategory,
    PostCategoryBase,
    PostCategoryCreate,
    PostVoteAnalytics,
    PostVoteStatistics,
    PostVoteStatisticsBase,
    PostVoteStatisticsCreate,
    Reaction,
    ReactionBase,
    ReactionCount,
    ReactionCreate,
    PollCreate,
    PollData,
    PollOption,
    PollResults,
    UserVoteAnalytics,
    PostBase,
    PostCreate,
    Post,
    PostOut,
    EngagementStats,
    SocialPostBase,
    SocialPostCreate,
    SocialPostUpdate,
    SocialPostOut,
    PostSearch,
)
from app.modules.users.schemas import (
    EmailChange,
    EmailSchema,
    FollowingListOut,
    FollowerOut,
    FollowersListOut,
    NotificationsSettings,
    PasswordChange,
    PasswordReset,
    PrivacyLevel,
    SecurityQuestionAnswer,
    SecurityQuestionsSet,
    SortOption,
    UserAnalytics,
    UserBanOut,
    UserBase,
    UserContentOut,
    UserCreate,
    UserFollowersSettings,
    UserLanguageUpdate,
    UserLogin,
    UserOut,
    UserPrivacyUpdate,
    UserProfileOut,
    UserProfileUpdate,
    UserPublicKeyUpdate,
    UserRole,
    UserRoleUpdate,
    UserSessionCreate,
    UserSessionOut,
    UserSettings,
    UserSettingsUpdate,
    UserStatisticsOut,
    UserUpdate,
    UserWarningOut,
    UISettings,
)


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
# Schemas for creating and representing hashtags and their statistics.
# ================================================================
class HashtagBase(BaseModel):
    name: str


class HashtagCreate(HashtagBase):
    pass


class Hashtag(HashtagBase):
    id: int
    followers_count: int

    model_config = ConfigDict(from_attributes=True)


# Hashtag statistics model
class HashtagStatistics(BaseModel):
    post_count: int
    follower_count: int
    engagement_rate: float


# ================================================================
# Search and Sorting Models
# Schemas used for search parameters and sorting options.
# ================================================================
# Parameters used for search queries
class SearchParams(BaseModel):
    query: str
    sort_by: SortOption = SortOption.RELEVANCE


# Settings for user followers display and sorting

# ================================================================
# Screen Share and Appeal Models
# Schemas related to screen sharing sessions and appeal processes.
# ================================================================
class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"



class ScreenShareStart(BaseModel):
    call_id: int


# Model for ending a screen share session
class ScreenShareEnd(BaseModel):
    session_id: int


# Update model for screen sharing (status and error message)
class ScreenShareUpdate(BaseModel):
    status: ScreenShareStatus
    error_message: Optional[str] = None


# Output model for screen share session details
class ScreenShareSessionOut(BaseModel):
    id: int
    call_id: int
    sharer_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: ScreenShareStatus
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Ban, Block, and Appeal Models
# Schemas for managing banned words, block appeals, and IP bans.
# ================================================================
class AppealStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WordSeverity(str, Enum):
    warn = "warn"
    ban = "ban"


# Base model for banned words
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


# Models for block appeals
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


class BlockStatistics(BaseModel):
    total_blocks: int
    active_blocks: int
    expired_blocks: int

    model_config = ConfigDict(from_attributes=True)


class BlockAppealReview(BaseModel):
    status: AppealStatus


# IP ban models
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


# Block models and logs
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
    current_screen_share: Optional[ScreenShareSessionOut] = None
    quality_score: int

    model_config = ConfigDict(from_attributes=True)


class AdvancedSearchQuery(BaseModel):
    keyword: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    categories: Optional[List[int]] = None
    author_id: Optional[int] = None
    search_in: List[str] = Field(default=["title", "content", "comments"])


# ================================================================
# Message and Notification Related Models
# Schemas for messages, notifications, and related attachments.
# ================================================================
class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    STICKER = "sticker"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


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


# Block duration and type models
class BlockDuration(str, Enum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


class BlockTypeEnum(str, Enum):
    FULL = "full"
    PARTIAL_COMMENT = "partial_comment"
    PARTIAL_MESSAGE = "partial_message"


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


# Ban statistics models
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


# Copyright types for posts
class CopyrightType(str, Enum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


# Model for blocked user details
class BlockedUserOut(BaseModel):
    id: int
    username: str
    email: str
    block_type: BlockTypeEnum
    reason: Optional[str]
    blocked_since: datetime

    model_config = ConfigDict(from_attributes=True)


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
# Schemas for handling search statistics and support tickets.
# ================================================================
class SearchStatOut(BaseModel):
    query: str
    count: int
    last_searched: datetime
    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    results: List["PostOut"]
    spell_suggestion: str
    search_suggestions: List[str]


class TicketCreate(BaseModel):
    subject: str
    description: str


class TicketResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    user: "UserOut"

    model_config = ConfigDict(from_attributes=True)


class Ticket(BaseModel):
    id: int
    subject: str
    description: str
    status: str  # Could be further defined (e.g., TicketStatus enum)
    created_at: datetime
    updated_at: datetime
    responses: List[TicketResponse]

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Warning and Ban Models for Users
# Schemas for user warnings and bans.
# ================================================================
class WarningCreate(BaseModel):
    reason: str


class BanCreate(BaseModel):
    reason: str




# ================================================================
# Base Models for Users, Posts, Comments, and Reports
# Core schemas for users, posts, comments, and report functionalities.
# ================================================================

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


# Models for search statistics of messages
class SearchStatisticsBase(BaseModel):
    query: str
    count: int
    last_searched: datetime


class SearchStatisticsCreate(SearchStatisticsBase):
    pass


class SearchStatistics(SearchStatisticsBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Article, Community, and Reel Models (Content Models)
# Schemas for articles, communities, and reels content.
# ================================================================
class ArticleBase(BaseModel):
    title: str
    content: str


from app.modules.community.schemas import (
    CommunityAnalytics,
    CommunityActivityAnalytics,
    CommunityBase,
    CommunityContentAnalysis,
    CommunityCreate,
    CommunityEngagementAnalytics,
    CommunityGrowthAnalytics,
    CommunityInvitationBase,
    CommunityInvitationCreate,
    CommunityInvitationOut,
    CommunityMemberBase,
    CommunityMemberCreate,
    CommunityMemberOut,
    CommunityMemberUpdate,
    CommunityOut,
    CommunityOutRef,
    CommunityOverview,
    CommunityOverviewAnalytics,
    CommunityRole,
    CommunityRuleBase,
    CommunityRuleCreate,
    CommunityRuleOut,
    CommunityRuleUpdate,
    CommunityStatistics,
    CommunityStatisticsBase,
    CommunityStatisticsCreate,
    CommunityUpdate,
)


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

class CommunityCreate(CommunityBase):
    category_id: Optional[int] = None
    tags: List[int] = []
    rules: Optional[List["CommunityRuleCreate"]] = None


class CommunityUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[List[int]] = None


class CommunityOut(CommunityBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut
    member_count: int
    members: List["CommunityMemberOut"]
    rules: List["CommunityRuleOut"] = []
    category: Optional["Category"] = None
    tags: List["Tag"]

    model_config = ConfigDict(from_attributes=True)



class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str




class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    name: str
    description: Optional[str] = None


class CategoryOut(CategoryCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class Category(CategoryBase):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class SearchSuggestionOut(BaseModel):
    term: str

    model_config = ConfigDict(from_attributes=True)


class AdvancedSearchResponse(BaseModel):
    total: int
    posts: List["PostOut"]


# Post category schemas live in app.modules.posts.schemas.
PostCategorySchema = PostCategory


class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CommunityStatisticsBase(BaseModel):
    date: date
    member_count: int
    post_count: int
    comment_count: int
    active_users: int
    total_reactions: int
    average_posts_per_user: float


class CommunityStatisticsCreate(CommunityStatisticsBase):
    pass


class CommunityStatistics(CommunityStatisticsBase):
    id: int
    community_id: int

    model_config = ConfigDict(from_attributes=True)


class CommunityOverview(BaseModel):
    id: int
    name: str
    description: str
    member_count: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CommunityRuleBase(BaseModel):
    rule: str


class CommunityRuleCreate(CommunityRuleBase):
    pass


class CommunityRuleUpdate(CommunityRuleBase):
    pass


class CommunityRuleOut(CommunityRuleBase):
    id: int
    community_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Community Analytics Models
# Schemas for analyzing community performance and engagement.
# ================================================================
class CommunityOverviewAnalytics(BaseModel):
    total_members: int
    active_members: int
    total_posts: int
    total_comments: int


class CommunityActivityAnalytics(BaseModel):
    date: str
    posts: int
    comments: int
    active_users: int


class CommunityEngagementAnalytics(BaseModel):
    avg_likes_per_post: float
    avg_comments_per_post: float
    total_shares: int


class CommunityContentAnalysis(BaseModel):
    type: str
    count: int
    avg_engagement: float


class CommunityGrowthAnalytics(BaseModel):
    date: str
    members: int


class CommunityAnalytics(BaseModel):
    overview: CommunityOverviewAnalytics
    activity: List[CommunityActivityAnalytics]
    engagement: CommunityEngagementAnalytics
    content_analysis: List[CommunityContentAnalysis]
    growth: List[CommunityGrowthAnalytics]


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
# Report Models
# Schemas for creating and reviewing reports on content.
# ================================================================
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
    status: "ReportStatus"
    resolution_notes: Optional[str] = None


class ReportOut(Report):
    status: "ReportStatus"
    reviewed_by: Optional[int]
    resolution_notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Message Models
# Schemas for message creation, update, and conversation details.
# ================================================================
class MessageCreate(MessageBase):
    receiver_id: int = Field(alias="recipient_id")
    attachments: List[MessageAttachmentCreate] = Field(default_factory=list)
    sticker_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    encrypted_content: str  # Encrypted content
    timestamp: datetime
    replied_to: Optional["Message"] = None
    quoted_message: Optional["Message"] = None
    is_edited: bool = False
    conversation_id: str
    link_preview: Optional["LinkPreview"] = None

    model_config = ConfigDict(from_attributes=True)


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


class LinkPreview(BaseModel):
    title: str
    description: Optional[str] = None
    image: Optional[str] = None
    url: str


# ================================================================
# Community Member and Role Models
# Schemas for managing community memberships and roles.
# ================================================================
class CommunityRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    VIP = "vip"
    MEMBER = "member"


class CommunityMemberBase(BaseModel):
    role: CommunityRole
    activity_score: int


class CommunityMemberCreate(CommunityMemberBase):
    user_id: int


class CommunityMemberUpdate(CommunityMemberBase):
    pass


class CommunityMemberOut(CommunityMemberBase):
    user: UserOut
    join_date: datetime

    model_config = ConfigDict(from_attributes=True)


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


class Reel(ReelBase):
    id: int
    created_at: datetime
    owner_id: int
    community_id: int
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)


class ReelOut(Reel):
    community: CommunityOutRef

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Community Invitation Models
# Schemas for handling community invitations.
# ================================================================
class CommunityInvitationBase(BaseModel):
    community_id: int
    invitee_id: int


class CommunityInvitationCreate(CommunityInvitationBase):
    pass


class CommunityInvitationOut(BaseModel):
    id: int
    community_id: int
    inviter_id: int
    invitee_id: int
    status: str
    created_at: datetime
    community: CommunityOutRef
    inviter: UserOut
    invitee: UserOut

    model_config = ConfigDict(from_attributes=True)


class CommunityInvitationResponse(BaseModel):
    accept: bool = Field(
        ...,
        description="Set to true to accept the invitation, false to decline it.",
    )


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

class ReportStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"








# ================================================================
# Sticker Models
# Schemas for creating and managing stickers and sticker packs.
# ================================================================
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


class Sticker(StickerBase):
    id: int
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


# ================================================================
# Resolve Forward References
# This section ensures that forward references are updated.
# ================================================================
Message.model_rebuild()
CommunityOut.model_rebuild()
ArticleOut.model_rebuild()
ReelOut.model_rebuild()
Post.model_rebuild()
PostOut.model_rebuild()
Comment.model_rebuild()
CommunityInvitationOut.model_rebuild()

# ================================================================
# Example Instance for Testing
# This block is for testing schema instantiation.
# ================================================================
if __name__ == "__main__":
    try:
        # Create an example PostOut instance for testing purposes
        post_example = PostOut(
            id=1,
            title="Sample Post",
            content="Content",
            published=True,
            created_at=datetime.now(),
            owner_id=1,
            community_id=1,
            owner=UserOut(
                id=1,
                email="test@example.com",
                created_at=datetime.now(),
                role=UserRole.USER,
                is_2fa_enabled=False,
                privacy_level=PrivacyLevel.PUBLIC,
                followers_count=0,
                is_verified=False,
            ),
            community=CommunityOut(
                id=1,
                name="Sample Community",
                description="A sample community",
                created_at=datetime.now(),
                owner_id=1,
                owner=UserOut(
                    id=1,
                    email="owner@example.com",
                    created_at=datetime.now(),
                    role=UserRole.ADMIN,
                    is_2fa_enabled=False,
                    privacy_level=PrivacyLevel.PUBLIC,
                    followers_count=0,
                    is_verified=True,
                ),
                member_count=1,
                members=[],
                category=Category(id=1, name="Sample Category", description=""),
                tags=[Tag(id=1, name="Sample Tag")],
            ),
            privacy_level=PrivacyLevel.PUBLIC,
            reactions=[],
            reaction_counts=[],
            has_best_answer=False,
            category=None,
            hashtags=[],
            repost_count=0,
            original_post=None,
            sentiment=None,
            sentiment_score=None,
            content_suggestion=None,
            mentioned_users=[],
            is_audio_post=False,
            audio_url=None,
            is_poll=False,
            poll_data=None,
            copyright_type=CopyrightType.ALL_RIGHTS_RESERVED,
            custom_copyright=None,
            is_archived=False,
            archived_at=None,
            media_url=None,
            media_type=None,
            media_text=None,
        )
        print("PostOut instance:", post_example)
    except Exception as e:
        print("Validation error:", e)





