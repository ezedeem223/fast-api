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
)
from datetime import datetime, date, timedelta, time
from typing import Optional, List, Dict, Tuple, Union, Any, ForwardRef
from enum import Enum

# ================================================================
# Reactions and Vote Models
# ================================================================


class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


# Base model for a reaction
class ReactionBase(BaseModel):
    reaction_type: ReactionType


# Model for creating a reaction (includes post id)
class ReactionCreate(ReactionBase):
    post_id: int


# Reaction model with id and user information
class Reaction(ReactionBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


# Model to count reactions of each type
class ReactionCount(BaseModel):
    reaction_type: ReactionType
    count: int


class EmailChange(BaseModel):
    new_email: EmailStr


class SecurityQuestionsSet(BaseModel):
    question1: str
    answer1: str
    question2: str
    answer2: str
    question3: str
    answer3: str


class SecurityQuestionAnswer(BaseModel):
    question: str
    answer: str


class FollowingListOut(BaseModel):
    following: List["UserOut"]
    total_count: int


# ================================================================
# Post Vote and Analytics Models
# ================================================================


class PostVoteStatisticsBase(BaseModel):
    total_votes: int
    upvotes: int
    downvotes: int
    like_count: int
    love_count: int
    haha_count: int
    wow_count: int
    sad_count: int
    angry_count: int


class PostVoteStatisticsCreate(PostVoteStatisticsBase):
    pass


class PostVoteStatistics(PostVoteStatisticsBase):
    id: int
    post_id: int
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


# Model to represent analytics of a post's votes
class PostVoteAnalytics(BaseModel):
    post_id: int
    title: str
    statistics: PostVoteStatistics
    upvote_percentage: float
    downvote_percentage: float
    most_common_reaction: str


# Aggregated vote analytics for a user
class UserVoteAnalytics(BaseModel):
    total_posts: int
    total_votes_received: int
    average_votes_per_post: float
    most_upvoted_post: PostVoteAnalytics
    most_downvoted_post: PostVoteAnalytics
    most_reacted_post: PostVoteAnalytics


# ================================================================
# Hashtag Models
# ================================================================


class HashtagBase(BaseModel):
    name: str


class HashtagCreate(HashtagBase):
    pass


class Hashtag(HashtagBase):
    id: int
    followers_count: int

    model_config = ConfigDict(from_attributes=True)


# نموذج إحصائيات الهاشتاج
class HashtagStatistics(BaseModel):
    post_count: int
    follower_count: int
    engagement_rate: float


# ================================================================
# Search and Sorting Models
# ================================================================


class SortOption(str, Enum):
    DATE = "date"
    USERNAME = "username"
    POST_COUNT = "post_count"
    INTERACTION_COUNT = "interaction_count"
    REPOST_COUNT = "repost_count"
    POPULARITY = "popularity"
    RELEVANCE = "relevance"
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"


# Parameters used for search queries
class SearchParams(BaseModel):
    query: str
    sort_by: SortOption = SortOption.RELEVANCE


# Settings for user followers display and sorting
class UserFollowersSettings(BaseModel):
    followers_visibility: str
    followers_custom_visibility: Optional[Dict[str, List[int]]] = None
    followers_sort_preference: SortOption


# ================================================================
# Screen Share and Appeal Models
# ================================================================


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScreenShareStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


# Model for starting a screen share session
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


class CommentStatistics(BaseModel):
    total_comments: int
    top_commenters: List[Tuple[int, str, int]]
    most_commented_posts: List[Tuple[int, str, int]]
    average_sentiment: float


# ================================================================
# Privacy and User Profile Models
# ================================================================


class PrivacyLevel(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    CUSTOM = "custom"


class UserPrivacyUpdate(BaseModel):
    privacy_level: PrivacyLevel
    custom_privacy: Optional[dict] = None


class UserProfileUpdate(BaseModel):
    profile_image: Optional[HttpUrl] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    website: Optional[HttpUrl] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None


class UserProfileOut(BaseModel):
    id: int
    email: str
    profile_image: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    joined_at: datetime
    post_count: int
    follower_count: int
    following_count: int
    community_count: int
    media_count: int
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class UserStatisticsOut(BaseModel):
    date: date
    post_count: int
    comment_count: int
    like_count: int
    view_count: int

    model_config = ConfigDict(from_attributes=True)


class UserAnalytics(BaseModel):
    total_posts: int
    total_comments: int
    total_likes: int
    total_views: int
    daily_statistics: List[UserStatisticsOut]

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Search and Ticket Models
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
# ================================================================


class WarningCreate(BaseModel):
    reason: str


class BanCreate(BaseModel):
    reason: str


class UserWarningOut(BaseModel):
    id: int
    user_id: int
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserBanOut(BaseModel):
    id: int
    user_id: int
    reason: str
    duration: timedelta
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Base Models for Users, Posts, Comments, and Reports
# ================================================================


class UserBase(BaseModel):
    email: EmailStr
    interests: Optional[List[str]] = None


class PostBase(BaseModel):
    title: str
    content: str
    published: bool = True
    original_post_id: Optional[int] = None
    is_repost: bool = False
    allow_reposts: bool = True
    copyright_type: CopyrightType = CopyrightType.ALL_RIGHTS_RESERVED
    custom_copyright: Optional[str] = None
    is_archived: bool = False


class CommentBase(BaseModel):
    content: str


class ReportBase(BaseModel):
    report_reason: str
    reason: str
    ai_detected: bool = False
    ai_confidence: Optional[float] = None


class ReportCreate(ReportBase):
    post_id: Optional[int] = None
    comment_id: Optional[int] = None


class ReportOut(ReportBase):
    id: int
    post_id: Optional[int]
    comment_id: Optional[int]
    reporter_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserPublicKeyUpdate(BaseModel):
    public_key: str


# ================================================================
# Message Attachment and Messaging Models
# ================================================================


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
    encrypted_content: str
    message_type: MessageType
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
    file_url: Optional[str]


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
# ================================================================


class ArticleBase(BaseModel):
    title: str
    content: str


class CommunityBase(BaseModel):
    name: constr(min_length=1)
    description: Optional[str] = None


class ReelBase(BaseModel):
    title: str
    video_url: str
    description: Optional[str] = None


# UI and Notification Settings
class UISettings(BaseModel):
    theme: Optional[str] = "light"
    language: Optional[str] = "en"
    font_size: Optional[str] = "medium"


class NotificationsSettings(BaseModel):
    email_notifications: bool = True
    push_notifications: bool = True
    newsletter: bool = True


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
    # This will be merged with PostCreate in the Post Models section
    repost_settings: Optional[RepostSettings] = None


# Preferences for notification updates
class NotificationPreferencesUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    categories_preferences: Optional[Dict[str, bool]] = None
    notification_frequency: Optional[str] = None


class NotificationPreferencesOut(BaseModel):
    id: int
    user_id: int
    email_notifications: bool
    push_notifications: bool
    in_app_notifications: bool
    quiet_hours_start: Optional[time]
    quiet_hours_end: Optional[time]
    categories_preferences: Dict[str, bool]
    notification_frequency: str
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


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
# ================================================================


# Enum for supported social media platforms
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


# Models for social posts
class SocialPostBase(BaseModel):
    title: Optional[str] = None
    content: str
    media_urls: Optional[List[HttpUrl]] = None
    scheduled_for: Optional[datetime] = None


class SocialPostCreate(SocialPostBase):
    platform: SocialMediaType


class SocialPostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    media_urls: Optional[List[HttpUrl]] = None
    scheduled_for: Optional[datetime] = None


class SocialPostOut(SocialPostBase):
    id: int
    user_id: int
    account_id: int
    platform_post_id: Optional[str]
    status: PostStatus
    error_message: Optional[str]
    engagement_stats: Dict
    created_at: datetime
    published_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class EngagementStats(BaseModel):
    upvotes: Optional[int]
    downvotes: Optional[int]
    comments: Optional[int]
    shares: Optional[int]
    likes: Optional[int]


# Notification models
class NotificationBase(BaseModel):
    content: str
    notification_type: str
    priority: Any  # Could be defined as an enum NotificationPriority
    category: Any  # Could be defined as an enum NotificationCategory


class NotificationCreate(NotificationBase):
    user_id: int
    link: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None
    notification_channel: Optional[str] = "in_app"
    importance_level: Optional[int] = 1


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_archived: Optional[bool] = None
    interaction_count: Optional[int] = None


class NotificationDeliveryStatus(BaseModel):
    success: bool
    channel: str
    timestamp: datetime
    error_message: Optional[str] = None


class NotificationStatistics(BaseModel):
    total_count: int
    unread_count: int
    categories_distribution: List[Tuple[str, int]]
    priorities_distribution: List[Tuple[str, int]]
    daily_notifications: List[Tuple[date, int]]


class NotificationAnalytics(BaseModel):
    engagement_rate: float
    response_time: float
    peak_activity_hours: List[Dict[str, Union[int, int]]]
    most_interacted_types: List[Dict[str, Union[str, int]]]


class NotificationGroupOut(BaseModel):
    id: int
    group_type: str
    count: int
    last_updated: datetime
    sample_notification: "NotificationOut"

    model_config = ConfigDict(from_attributes=True)


class NotificationDeliveryLogOut(BaseModel):
    id: int
    attempt_time: datetime
    status: str
    error_message: Optional[str]
    delivery_channel: str

    model_config = ConfigDict(from_attributes=True)


class NotificationWithLogs(BaseModel):
    delivery_logs: List[NotificationDeliveryLogOut]
    retry_count: int
    status: Any  # Could be defined as NotificationStatus enum
    last_retry: Optional[datetime] = None


class NotificationOut(BaseModel):
    id: int
    content: str
    notification_type: str
    priority: Any
    category: Any
    link: Optional[str]
    is_read: bool
    is_archived: bool
    read_at: Optional[datetime]
    created_at: datetime
    group: Optional[NotificationGroupOut]
    metadata: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


# User settings models
class UserSettings(BaseModel):
    ui_settings: UISettings
    notifications_settings: NotificationsSettings


class UserSettingsUpdate(BaseModel):
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]


# ================================================================
# User Models
# ================================================================


class UserCreate(UserBase):
    password: str
    email: EmailStr
    public_key: str


class UserUpdate(BaseModel):
    hide_read_status: Optional[bool] = None
    phone_number: Optional[str] = None
    followers_settings: Optional[UserFollowersSettings] = None
    followed_hashtags: List[int] = []
    allow_reposts: Optional[bool] = None


class UserLogin(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    created_at: datetime
    email: EmailStr
    role: "UserRole"
    is_2fa_enabled: bool
    privacy_level: PrivacyLevel
    custom_privacy: Optional[dict] = None
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]
    public_key: Optional[str] = None  # Public key field
    followers_count: int
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)


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
# ================================================================


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[int] = None


# ================================================================
# Vote Models
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
# ================================================================

CommunityOutRef = ForwardRef("CommunityOut")


class CommunityCreate(CommunityBase):
    category_id: int
    tags: List[int] = []


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
    category: "Category"
    tags: List["Tag"]

    model_config = ConfigDict(from_attributes=True)


class UserLanguageUpdate(BaseModel):
    preferred_language: str
    auto_translate: bool = True


class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str


class FollowerOut(BaseModel):
    id: int
    username: str
    follow_date: datetime
    post_count: int
    interaction_count: int

    model_config = ConfigDict(from_attributes=True)


class FollowersListOut(BaseModel):
    followers: List[FollowerOut]
    total_count: int


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


class PostCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    hashtags: List[str] = []
    analyze_content: bool = Field(
        default=False, description="Flag to trigger content analysis"
    )


class PostCategoryCreate(PostCategoryBase):
    pass


class PostCategory(PostCategoryBase):
    id: int
    children: List["PostCategory"] = []

    model_config = ConfigDict(from_attributes=True)


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
# ================================================================


class PostCreate(PostBase):
    community_id: Optional[int] = None
    hashtags: List[str] = []
    is_help_request: bool = False
    category_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None
    content: str
    mentioned_usernames: List[str] = []


class Post(PostBase):
    id: int
    created_at: datetime
    owner_id: int
    community_id: Optional[int]
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)


class PostOut(Post):
    community: Optional[CommunityOutRef]
    privacy_level: PrivacyLevel
    reactions: List[Reaction] = []
    reaction_counts: List[ReactionCount] = []
    has_best_answer: bool = False
    category: Optional[PostCategory] = None
    hashtags: List[Hashtag] = []
    repost_count: int
    original_post: Optional["PostOut"] = None
    sentiment: Optional[str]
    sentiment_score: Optional[float]
    content_suggestion: Optional[str]
    mentioned_users: List[UserOut]
    is_audio_post: bool
    audio_url: Optional[str]
    is_poll: bool
    poll_data: Optional["PollData"]
    copyright_type: CopyrightType
    custom_copyright: Optional[str]
    is_archived: bool
    archived_at: Optional[datetime]
    media_url: Optional[str]
    media_type: Optional[str]
    media_text: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class PollOption(BaseModel):
    id: int
    option_text: str


class PollData(BaseModel):
    options: List[PollOption]
    end_date: Optional[datetime]


class PollCreate(BaseModel):
    title: str
    description: str
    options: List[str]
    end_date: Optional[datetime]


class PollResults(BaseModel):
    post_id: int
    total_votes: int
    results: List[Dict[str, Union[int, str, float]]]
    is_ended: bool
    end_date: Optional[datetime]


# ================================================================
# Comment Models
# ================================================================


class CommentCreate(CommentBase):
    content: str
    post_id: int
    parent_id: Optional[int] = None
    image_url: Optional[HttpUrl] = None
    video_url: Optional[HttpUrl] = None
    sticker_id: Optional[int] = None


class CommentOut(BaseModel):
    contains_profanity: bool
    has_invalid_urls: bool
    reported_count: int
    likes_count: int
    is_flagged: bool
    flag_reason: Optional[str] = None
    reactions: List[Reaction] = []
    reaction_counts: List[ReactionCount] = []
    is_highlighted: bool = False
    is_best_answer: bool = False
    image_url: Optional[HttpUrl] = None
    video_url: Optional[HttpUrl] = None
    has_emoji: bool
    has_sticker: bool
    sticker: Optional[Any] = None  # Expected to be a StickerOut model
    is_pinned: bool = False
    pinned_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FlagCommentRequest(BaseModel):
    flag_reason: str = Field(..., min_length=5, max_length=200)


class CommentUpdate(CommentBase):
    pass


class CommentEditHistoryOut(BaseModel):
    id: int
    previous_content: str
    edited_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Comment(CommentBase):
    id: int
    created_at: datetime
    owner_id: int
    post_id: int
    parent_id: Optional[int]
    is_edited: bool
    edited_at: Optional[datetime]
    is_deleted: bool
    deleted_at: Optional[datetime]
    edit_history: List[CommentEditHistoryOut] = []
    replies: List["Comment"] = []

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Report Models
# ================================================================


class Report(ReportBase):
    id: int
    created_at: datetime
    reporter_id: int

    model_config = ConfigDict(from_attributes=True)


class ReportReview(BaseModel):
    is_valid: bool


class UserRoleUpdate(BaseModel):
    role: "UserRole"


class ReportUpdate(BaseModel):
    status: "ReportStatus"
    resolution_notes: Optional[str] = None


class ReportOut(ReportBase):
    id: int
    report_reason: str
    post_id: Optional[int]
    comment_id: Optional[int]
    reporter_id: int
    created_at: datetime
    status: "ReportStatus"
    reviewed_by: Optional[int]
    resolution_notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# Message Models
# ================================================================


class MessageCreate(MessageBase):
    receiver_id: int
    encrypted_content: str  # Encrypted content instead of plain text
    message_type: MessageType
    attachments: List[MessageAttachmentCreate] = []


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


class MessageSearch(BaseModel):
    query: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    message_type: Optional[MessageType] = None
    conversation_id: Optional[str] = None
    sort_order: SortOrder = SortOrder.DESC


class MessageSearchResponse(BaseModel):
    total: int
    messages: List[Message]


class MessageUpdate(BaseModel):
    content: str


class MessageOut(BaseModel):
    message: Message
    count: int

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


# ================================================================
# 2FA Models
# ================================================================


class Enable2FAResponse(BaseModel):
    otp_secret: str


class Verify2FARequest(BaseModel):
    otp: str


class Verify2FAResponse(BaseModel):
    message: str


# ================================================================
# Additional User Session and Authentication Models
# ================================================================


class UserRole(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class ReportStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class UserSessionCreate(BaseModel):
    session_id: str
    ip_address: str
    user_agent: str


class UserSessionOut(UserSessionCreate):
    id: int
    user_id: int
    created_at: datetime
    last_activity: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class EmailSchema(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str


class UserContentOut(BaseModel):
    posts: List[PostOut]
    comments: List[Comment]
    articles: List[ArticleOut]
    reels: List[ReelOut]

    model_config = ConfigDict(from_attributes=True)


class PostSearch(BaseModel):
    keyword: Optional[str] = None
    category_id: Optional[int] = None


# ================================================================
# Sticker Models
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
# ================================================================
Message.update_forward_refs()
CommunityOut.model_rebuild()
ArticleOut.model_rebuild()
ReelOut.model_rebuild()
PostOut.model_rebuild()
PostOut.update_forward_refs()
Comment.update_forward_refs()
CommunityInvitationOut.model_rebuild()

# ================================================================
# Example Instance for Testing
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
    except ValidationError as e:
        print("Validation error:", e)
