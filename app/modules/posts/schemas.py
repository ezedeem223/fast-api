"""Pydantic schemas for posts reactions and vote analytics."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, constr

from app.modules.posts.models import (
    CopyrightType,
    PostStatus,
    ReactionType,
    SocialMediaType,
)
from app.modules.users.schemas import PrivacyLevel

if TYPE_CHECKING:  # pragma: no cover
    from app.schemas import (
        CommunityOutRef,
        Hashtag,
        UserOut,
    )


class ReactionBase(BaseModel):
    reaction_type: ReactionType


class ReactionCreate(ReactionBase):
    post_id: int


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
    most_upvoted_post: Optional[PostVoteAnalytics]
    most_downvoted_post: Optional[PostVoteAnalytics]
    most_reacted_post: Optional[PostVoteAnalytics]


class HashtagBase(BaseModel):
    name: str


class HashtagCreate(HashtagBase):
    pass


class Hashtag(HashtagBase):
    id: int
    followers_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class HashtagStatistics(BaseModel):
    post_count: int
    follower_count: int
    engagement_rate: float


class PostCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    hashtags: List[str] = Field(
        default_factory=list, description="Associated hashtag names"
    )
    analyze_content: bool = Field(
        default=False, description="Flag to trigger content analysis"
    )


class PostCategoryCreate(PostCategoryBase):
    pass


class PostCategory(PostCategoryBase):
    id: int
    children: List["PostCategory"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


PostCategory.model_rebuild()


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


class PostBase(BaseModel):
    title: constr(min_length=1, max_length=300)
    content: str
    published: bool = True
    original_post_id: Optional[int] = None
    is_repost: bool = False
    allow_reposts: bool = True
    copyright_type: CopyrightType = CopyrightType.ALL_RIGHTS_RESERVED
    custom_copyright: Optional[str] = None
    is_archived: bool = False
    is_encrypted: bool = False
    encryption_key_id: Optional[str] = None
    is_living_testimony: bool = False


class PostCreate(PostBase):
    community_id: Optional[int] = None
    hashtags: List[str] = Field(default_factory=list)
    related_to_post_id: Optional[int] = None  # لربط المنشور بمنشور قديم
    relation_type: Optional[str] = "continuation"  # نوع العلاقة (استكمال، رد...)
    is_help_request: bool = False
    category_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None
    content: str
    mentioned_usernames: List[str] = Field(default_factory=list)
    analyze_content: bool = False


class Post(PostBase):
    id: int
    created_at: datetime
    owner_id: int
    community_id: Optional[int]
    owner: "UserOut"

    model_config = ConfigDict(from_attributes=True)


class PostRelationOut(BaseModel):
    """Schema for displaying a related memory (Living Memory)."""

    target_post_id: int
    similarity_score: float
    relation_type: str
    created_at: datetime
    # نقوم بتضمين تفاصيل المنشور القديم (الذكرى)
    # نستخدم 'Post' هنا لأنها معرفة بالأعلى، مما يتجنب المشاكل الدائرية
    target_post: Optional[Post] = None

    model_config = ConfigDict(from_attributes=True)


class PostOut(Post):
    community: Optional["CommunityOutRef"] = None
    privacy_level: PrivacyLevel = PrivacyLevel.PUBLIC
    reactions: List[Reaction] = Field(default_factory=list)
    reaction_counts: List[ReactionCount] = Field(default_factory=list)
    has_best_answer: bool = False
    category: Optional[PostCategory] = None
    hashtags: List["Hashtag"] = Field(default_factory=list)
    repost_count: int = 0
    original_post: Optional["PostOut"] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    content_suggestion: Optional[str] = None
    mentioned_users: List["UserOut"] = Field(default_factory=list)
    is_audio_post: bool = False
    audio_url: Optional[str] = None
    is_poll: bool = False
    poll_data: Optional["PollData"] = None
    custom_copyright: Optional[str] = None
    is_archived: bool = False
    archived_at: Optional[datetime] = None
    is_encrypted: bool = False
    encryption_key_id: Optional[str] = None
    is_living_testimony: bool = False
    living_testimony: Optional["LivingTestimonyOut"] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    media_text: Optional[str] = None
    media_text: Optional[str] = None
    related_memories: List[PostRelationOut] = Field(default_factory=list)
    quality_score: Optional[float] = 0.0
    originality_score: Optional[float] = 0.0
    # score موجود بالفعل في المخطط، فلا داعي لإضافته
    model_config = ConfigDict(from_attributes=True)


class EngagementStats(BaseModel):
    upvotes: Optional[int]
    downvotes: Optional[int]
    comments: Optional[int]
    shares: Optional[int]
    likes: Optional[int]


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
    engagement_stats: Dict[str, Union[int, float, None]]
    created_at: datetime
    published_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PostSearch(BaseModel):
    keyword: Optional[str] = None
    category_id: Optional[int] = None
    hashtag: Optional[str] = None


class LivingTestimonyOut(BaseModel):
    id: int
    post_id: int
    verified_by_user_id: Optional[int] = None
    historical_event: Optional[str] = None
    geographic_location: Optional[str] = None
    recorded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CommentStatistics(BaseModel):
    total_comments: int
    top_commenters: List[Tuple[int, str, int]]
    most_commented_posts: List[Tuple[int, str, int]]
    average_sentiment: float


class CommentBase(BaseModel):
    content: str


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
    sticker: Optional[Any] = None
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


class TimelinePoint(BaseModel):
    year: int
    month: int
    posts_count: int
    total_score: float

    model_config = ConfigDict(from_attributes=True)


class MemoryItem(BaseModel):
    post_id: int
    title: str
    snippet: str
    created_at: datetime
    years_ago: int
    type: str

    model_config = ConfigDict(from_attributes=True)
