from pydantic import BaseModel, EmailStr, conint, ValidationError, ConfigDict, constr
from datetime import datetime
from typing import Optional, List, ForwardRef
from enum import Enum


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


# User models
class UserCreate(UserBase):
    password: str


class UserLogin(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    created_at: datetime
    role: UserRole
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
    pass


class CommunityUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None
    description: Optional[str] = None


class CommunityOut(CommunityBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut
    member_count: int
    members: List[CommunityMemberOut]
    rules: List[CommunityRuleOut] = []

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
    role: UserRole


class ReportUpdate(BaseModel):
    status: ReportStatus
    resolution_notes: Optional[str] = None


class ReportOut(BaseModel):
    id: int
    report_reason: str
    post_id: Optional[int]
    comment_id: Optional[int]
    reporter_id: int
    created_at: datetime
    status: ReportStatus
    reviewed_by: Optional[int]
    resolution_notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# Message models
class MessageCreate(MessageBase):
    recipient_id: int


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    timestamp: datetime
    sender: Optional[UserOut]
    receiver: Optional[UserOut]

    model_config = ConfigDict(from_attributes=True)


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
    community: "CommunityOut"
    inviter: "UserOut"
    invitee: "UserOut"
    model_config = ConfigDict(from_attributes=True)


CommunityOut.model_rebuild()
CommunityInvitationOut.model_rebuild()


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


# Resolve forward references
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
            owner=UserOut(id=1, email="test@example.com", created_at=datetime.now()),
            community=CommunityOut(
                id=1,
                name="Sample Community",
                description="A sample community",
                created_at=datetime.now(),
                owner_id=1,
                owner=UserOut(
                    id=1, email="owner@example.com", created_at=datetime.now()
                ),
                member_count=1,
                members=[],
            ),
        )
        print("PostOut instance:", post_example)

    except ValidationError as e:
        print("Validation error:", e)
