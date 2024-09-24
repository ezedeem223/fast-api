from pydantic import BaseModel, EmailStr, conint, ValidationError, ConfigDict, constr
from datetime import datetime
from typing import Optional, List

# Redefining classes with the same structure to simulate validation and check for issues


class PostBase(BaseModel):
    title: str
    content: str
    published: bool = True


class PostCreate(PostBase):
    pass


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Post(PostBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)


class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: int
    created_at: datetime
    owner_id: int
    post_id: int
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)


class PostOut(BaseModel):
    post: Post
    votes: int

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[int] = None


class Vote(BaseModel):
    post_id: int
    dir: conint(le=1)


class ReportBase(BaseModel):
    report_reason: str


class ReportCreate(ReportBase):
    post_id: Optional[int] = None
    comment_id: Optional[int] = None


class Report(ReportBase):
    id: int
    created_at: datetime
    reporter_id: int

    model_config = ConfigDict(from_attributes=True)


class Enable2FAResponse(BaseModel):
    otp_secret: str


class Verify2FARequest(BaseModel):
    otp: str


class Verify2FAResponse(BaseModel):
    message: str


class MessageBase(BaseModel):
    content: constr(max_length=1000)


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


# Community models
class CommunityBase(BaseModel):
    name: constr(min_length=1)
    description: Optional[str] = None


class CommunityCreate(CommunityBase):
    pass


class CommunityUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None
    description: Optional[str] = None


class Community(CommunityBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut
    members: List[UserOut]

    model_config = ConfigDict(from_attributes=True)


class CommunityOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    owner_id: int
    owner: UserOut
    member_count: int
    members: List[UserOut]

    model_config = ConfigDict(from_attributes=True)


class CommunityList(BaseModel):
    communities: List[CommunityOut]
    total: int

    model_config = ConfigDict(from_attributes=True)


# Simulate an instance of some models to ensure they validate correctly
try:
    # Example instances
    post_example = PostOut(
        post=Post(
            id=1,
            title="Sample Post",
            content="Content",
            published=True,
            created_at=datetime.now(),
            owner_id=1,
            owner=UserOut(id=1, email="test@example.com", created_at=datetime.now()),
        ),
        votes=10,
    )
    community_example = CommunityOut(
        id=1,
        name="Community Name",
        description="Community Description",
        created_at=datetime.now(),
        owner_id=1,
        owner=UserOut(id=1, email="owner@example.com", created_at=datetime.now()),
        member_count=50,
    )

    print("PostOut instance:", post_example)
    print("CommunityOut instance:", community_example)

except ValidationError as e:
    print("Validation error:", e)
