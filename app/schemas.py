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
from datetime import datetime, date
from typing import Optional, List, ForwardRef, Dict
from enum import Enum


class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class ReactionBase(BaseModel):
    reaction_type: ReactionType


class ReactionCreate(ReactionBase):
    post_id: int
    reaction_type: ReactionType


class Reaction(ReactionBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class ReactionCount(BaseModel):
    reaction_type: ReactionType
    count: int


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


class PostVoteAnalytics(BaseModel):
    post_id: int
    title: str
    statistics: PostVoteStatistics
    upvote_percentage: float
    downvote_percentage: float
    most_common_reaction: str


class UserVoteAnalytics(BaseModel):
    total_posts: int
    total_votes_received: int
    average_votes_per_post: float
    most_upvoted_post: PostVoteAnalytics
    most_downvoted_post: PostVoteAnalytics
    most_reacted_post: PostVoteAnalytics


class HashtagBase(BaseModel):
    name: str


class HashtagCreate(HashtagBase):
    pass


class Hashtag(HashtagBase):
    id: int
    followers_count: int

    model_config = ConfigDict(from_attributes=True)


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


class SearchParams(BaseModel):
    query: str
    sort_by: SortOption = SortOption.RELEVANCE


class UserFollowersSettings(BaseModel):
    followers_visibility: str
    followers_custom_visibility: Optional[Dict[str, List[int]]] = None
    followers_sort_preference: SortOption


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScreenShareStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


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


class AppealStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


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


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    STICKER = "sticker"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class BusinessRegistration(BaseModel):
    business_name: str
    business_registration_number: str
    bank_account_info: str


class FollowStatistics(BaseModel):
    followers_count: int
    following_count: int
    daily_growth: Dict[date, int]
    interaction_rate: float


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


class CopyrightType(str, Enum):
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"


class BlockedUserOut(BaseModel):
    id: int
    username: str
    email: str
    block_type: BlockTypeEnum
    reason: Optional[str]
    blocked_since: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessVerificationUpdate(BaseModel):
    id_document: UploadFile
    passport: UploadFile
    business_document: UploadFile
    selfie: UploadFile


class BusinessUserOut(UserOut):
    business_name: str
    business_registration_number: str
    verification_status: VerificationStatus
    is_verified_business: bool


class BusinessTransactionCreate(BaseModel):
    client_user_id: int
    amount: float


class BusinessTransactionOut(BaseModel):
    id: int
    business_user: UserOut
    client_user: UserOut
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


class SearchStatOut(BaseModel):
    query: str
    count: int
    last_searched: datetime
    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    results: List[PostOut]
    spell_suggestion: str
    search_suggestions: List[str]


class TicketCreate(BaseModel):
    subject: str
    description: str


class TicketResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    user: UserOut

    model_config = ConfigDict(from_attributes=True)


class Ticket(BaseModel):
    id: int
    subject: str
    description: str
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    responses: List[TicketResponse]

    model_config = ConfigDict(from_attributes=True)


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


# Base models
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


class UISettings(BaseModel):
    theme: Optional[str] = "light"
    language: Optional[str] = "en"
    font_size: Optional[str] = "medium"


class NotificationsSettings(BaseModel):
    email_notifications: bool = True
    push_notifications: bool = True
    newsletter: bool = True


class RepostStatisticsOut(BaseModel):
    post_id: int
    repost_count: int
    last_reposted: datetime

    model_config = ConfigDict(from_attributes=True)


class RepostSettings(BaseModel):
    scope: str = "public"
    community_id: Optional[int] = None
    visibility: Optional[str] = "all_members"
    custom_message: Optional[str] = None


class RepostCreate(PostCreate):
    repost_settings: Optional[RepostSettings] = None


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


class AmenhotepMessageCreate(BaseModel):
    message: str


class AmenhotepMessageOut(BaseModel):
    id: int
    user_id: int
    message: str
    response: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationBase(BaseModel):
    content: str
    notification_type: str
    priority: NotificationPriority
    category: NotificationCategory


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


class NotificationWithLogs(NotificationOut):
    delivery_logs: List[NotificationDeliveryLogOut]
    retry_count: int
    status: NotificationStatus
    last_retry: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseModel):
    id: int
    content: str
    notification_type: str
    priority: NotificationPriority
    category: NotificationCategory
    link: Optional[str]
    is_read: bool
    is_archived: bool
    read_at: Optional[datetime]
    created_at: datetime
    group: Optional[NotificationGroupOut]
    metadata: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class UserSettings(BaseModel):
    ui_settings: UISettings
    notifications_settings: NotificationsSettings


class UserSettingsUpdate(BaseModel):
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]


# User models
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
    model_config = ConfigDict(from_attributes=True)
    privacy_level: PrivacyLevel
    custom_privacy: Optional[dict] = None
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]
    public_key: Optional[str] = None  # إضافة حقل المفتاح العام
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


# Token models
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[int] = None


# Vote model
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


# Community models
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
    posts: List[PostOut]


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


# Post models
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
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut
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
    model_config = ConfigDict(from_attributes=True)
    is_poll: bool
    poll_data: Optional[PollData]
    copyright_type: CopyrightType
    custom_copyright: Optional[str]
    is_archived: bool
    archived_at: Optional[datetime]
    media_url: Optional[str]
    media_type: Optional[str]
    media_text: Optional[str]


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


# Comment models
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
    model_config = ConfigDict(from_attributes=True)
    is_highlighted: bool = False
    is_best_answer: bool = False
    image_url: Optional[HttpUrl] = None
    video_url: Optional[HttpUrl] = None
    has_emoji: bool
    has_sticker: bool
    sticker: Optional[StickerOut] = None
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


# Report models
class ReportCreate(ReportBase):
    post_id: Optional[int] = None
    comment_id: Optional[int] = None


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


class ReportOut(BaseModel):
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


# Message models
class MessageCreate(MessageBase):
    receiver_id: int
    encrypted_content: str  # محتوى مشفر بدلاً من النص العادي
    message_type: MessageType
    attachments: List[MessageAttachmentCreate] = []


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    encrypted_content: str  # محتوى مشفر
    timestamp: datetime
    replied_to: Optional["Message"] = None
    quoted_message: Optional["Message"] = None
    is_edited: bool = False
    conversation_id: str
    link_preview: Optional[LinkPreview] = None

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


# Article models
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


# Reel models
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


# Community Invitation models
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


# 2FA models
class Enable2FAResponse(BaseModel):
    otp_secret: str


class Verify2FARequest(BaseModel):
    otp: str


class Verify2FAResponse(BaseModel):
    message: str


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
    categories: List[StickerCategory]

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


# Resolve forward references
Message.update_forward_refs()
CommunityOut.model_rebuild()
ArticleOut.model_rebuild()
ReelOut.model_rebuild()
PostOut.model_rebuild()
PostOut.update_forward_refs()
Comment.update_forward_refs()
CommunityInvitationOut.model_rebuild()

# Example instances for testing
if __name__ == "__main__":
    try:
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
                ),
                member_count=1,
                members=[],
                category=Category(id=1, name="Sample Category"),
                tags=[Tag(id=1, name="Sample Tag")],
            ),
        )
        print("PostOut instance:", post_example)

    except ValidationError as e:
        print("Validation error:", e)
