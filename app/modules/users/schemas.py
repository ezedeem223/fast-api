"""Pydantic schemas for the users domain."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, HttpUrl

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.posts.schemas import Comment as PostComment
    from app.modules.posts.schemas import PostOut
    from app.schemas import ArticleOut, ReelOut


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


class UserFollowersSettings(BaseModel):
    followers_visibility: str
    followers_custom_visibility: Optional[Dict[str, List[int]]] = None
    followers_sort_preference: SortOption = SortOption.RELEVANCE


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


class UISettings(BaseModel):
    theme: Optional[str] = "light"
    language: Optional[str] = "en"
    font_size: Optional[str] = "medium"


class NotificationsSettings(BaseModel):
    email_notifications: bool = True
    push_notifications: bool = True
    newsletter: bool = True


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


class UserBase(BaseModel):
    email: EmailStr
    interests: Optional[List[str]] = None


class UserPublicKeyUpdate(BaseModel):
    public_key: str


class UserSettings(BaseModel):
    ui_settings: UISettings
    notifications_settings: NotificationsSettings


class UserSettingsUpdate(BaseModel):
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]


class UserCreate(UserBase):
    password: str
    email: EmailStr
    public_key: Optional[str] = None


class UserUpdate(BaseModel):
    hide_read_status: Optional[bool] = None
    phone_number: Optional[str] = None
    followers_settings: Optional[UserFollowersSettings] = None
    followed_hashtags: List[int] = []
    allow_reposts: Optional[bool] = None


class UserLogin(UserBase):
    password: str


class UserRole(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class UserOut(UserBase):
    id: int
    created_at: datetime
    email: EmailStr
    role: UserRole
    is_2fa_enabled: bool
    privacy_level: PrivacyLevel
    custom_privacy: Optional[dict] = None
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]
    public_key: Optional[str] = None
    followers_count: int
    is_verified: bool
    social_credits: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class UserLanguageUpdate(BaseModel):
    preferred_language: str
    auto_translate: bool = True


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


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserSessionCreate(BaseModel):
    session_id: str
    ip_address: Optional[str]
    user_agent: Optional[str]


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
    posts: List["PostOut"]
    comments: List["PostComment"]
    articles: List["ArticleOut"]
    reels: List["ReelOut"]

    model_config = ConfigDict(from_attributes=True)


class IdentityLinkCreate(BaseModel):
    linked_user_id: int
    relationship_type: str = "alias"  # alias, business, backup


class IdentityOut(BaseModel):
    id: int
    linked_user_id: int
    relationship_type: str
    linked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataExportOut(BaseModel):
    user: dict
    posts: List[dict]
    comments: List[dict]
    identities: List[IdentityOut] = []
