"""Community domain Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, ForwardRef, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr
from app.modules.users.schemas import UserOut


CommunityOutRef = ForwardRef("CommunityOut")


class CommunityBase(BaseModel):
    name: constr(min_length=1)
    description: Optional[str] = None


class CommunityCreate(CommunityBase):
    category_id: Optional[int] = Field(default=None)
    tags: List[int] = Field(default_factory=list)


class CommunityUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[List[int]] = None


class CommunityOut(CommunityBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: "UserOut"
    member_count: int
    members: List["CommunityMemberOut"]
    rules: List["CommunityRuleOut"] = []
    category: Optional[Any] = None
    tags: List[Any] = Field(default_factory=list)

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
    user: "UserOut"
    join_date: datetime

    model_config = ConfigDict(from_attributes=True)


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
    inviter: "UserOut"
    invitee: "UserOut"

    model_config = ConfigDict(from_attributes=True)


class CommunityInvitationResponse(BaseModel):
    accept: bool = Field(
        ...,
        description="Set to true to accept the invitation, false to decline it.",
    )


__all__ = [
    "CommunityAnalytics",
    "CommunityActivityAnalytics",
    "CommunityBase",
    "CommunityContentAnalysis",
    "CommunityCreate",
    "CommunityEngagementAnalytics",
    "CommunityGrowthAnalytics",
    "CommunityInvitationBase",
    "CommunityInvitationCreate",
    "CommunityInvitationOut",
    "CommunityInvitationResponse",
    "CommunityMemberBase",
    "CommunityMemberCreate",
    "CommunityMemberOut",
    "CommunityMemberUpdate",
    "CommunityOut",
    "CommunityOutRef",
    "CommunityOverview",
    "CommunityOverviewAnalytics",
    "CommunityRole",
    "CommunityRuleBase",
    "CommunityRuleCreate",
    "CommunityRuleOut",
    "CommunityRuleUpdate",
    "CommunityStatistics",
    "CommunityStatisticsBase",
    "CommunityStatisticsCreate",
    "CommunityUpdate",
]
