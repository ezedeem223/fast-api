from pydantic import BaseModel, EmailStr, conint
from datetime import datetime
from typing import Optional, List


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

    class Config:
        orm_mode = True


class Post(PostBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


class PostOut(BaseModel):
    post: Post
    votes: int

    class Config:
        orm_mode = True


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
    user_id: Optional[int] = None


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

    class Config:
        orm_mode = True


class Enable2FAResponse(BaseModel):
    otp_secret: str


class Verify2FARequest(BaseModel):
    otp: str


class Verify2FAResponse(BaseModel):
    message: str


class MessageBase(BaseModel):
    content: str
    receiver_id: int
    sender_id: int


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: int
    created_at: datetime
    sender: UserOut
    receiver: UserOut

    class Config:
        orm_mode = True


class MessageOut(BaseModel):
    message: Message
    count: int

    class Config:
        orm_mode = True


# Community models
class CommunityBase(BaseModel):
    name: str
    description: Optional[str] = None


class CommunityCreate(CommunityBase):
    pass


class Community(CommunityBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut

    class Config:
        orm_mode = True


class CommunityOut(BaseModel):
    community: Community
    member_count: int

    class Config:
        orm_mode = True
