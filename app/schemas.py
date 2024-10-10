from pydantic import BaseModel, EmailStr, conint, ValidationError, ConfigDict, constr
from datetime import datetime, date
from typing import Optional, List, ForwardRef
from enum import Enum


class BusinessRegistration(BaseModel):
    business_name: str
    business_registration_number: str
    bank_account_info: str


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


# Base models
class UserBase(BaseModel):
    email: EmailStr


class PostBase(BaseModel):
    title: str
    content: str
    published: bool = True


class CommentBase(BaseModel):
    content: str


class ReportBase(BaseModel):
    report_reason: str


class MessageBase(BaseModel):
    content: constr(max_length=1000)
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


class UserSettings(BaseModel):
    ui_settings: UISettings
    notifications_settings: NotificationsSettings


class UserSettingsUpdate(BaseModel):
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]


# User models
class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    hide_read_status: Optional[bool] = None


class UserLogin(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    created_at: datetime
    role: "UserRole"
    is_2fa_enabled: bool
    model_config = ConfigDict(from_attributes=True)
    privacy_level: PrivacyLevel
    custom_privacy: Optional[dict] = None
    ui_settings: Optional[UISettings]
    notifications_settings: Optional[NotificationsSettings]

    model_config = ConfigDict(from_attributes=True)


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


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class Category(CategoryBase):
    id: int

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


# Post models
class PostCreate(PostBase):
    community_id: Optional[int] = None


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

    model_config = ConfigDict(from_attributes=True)


# Comment models
class CommentCreate(CommentBase):
    post_id: int


class Comment(CommentBase):
    id: int
    created_at: datetime
    owner_id: int
    post_id: int
    owner: UserOut

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


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    timestamp: datetime
    replied_to: Optional["Message"] = None
    quoted_message: Optional["Message"] = None
    is_edited: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageUpdate(BaseModel):
    content: str


class MessageOut(BaseModel):
    message: Message
    count: int

    model_config = ConfigDict(from_attributes=True)


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


# Resolve forward references
Message.update_forward_refs()
CommunityOut.model_rebuild()
ArticleOut.model_rebuild()
ReelOut.model_rebuild()
PostOut.model_rebuild()
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
