"""Community domain Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, ForwardRef, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr

from app.modules.users.schemas import UserOut

CommunityOutRef = ForwardRef("CommunityOut")


class CommunityBase(BaseModel):
    """Pydantic schema for CommunityBase."""
    name: constr(min_length=1)
    description: Optional[str] = None


class CommunityCreate(CommunityBase):
    """Pydantic schema for CommunityCreate."""
    category_id: Optional[int] = Field(default=None)
    tags: List[int] = Field(default_factory=list)


class CommunityUpdate(BaseModel):
    """Pydantic schema for CommunityUpdate."""
    name: Optional[constr(min_length=1)] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[List[int]] = None
    is_active: Optional[bool] = None


class CommunitySettingsUpdate(BaseModel):
    """Schema for updating community settings."""

    is_private: Optional[bool] = None
    requires_approval: Optional[bool] = None
    language: Optional[str] = None


class CommunityRuleBase(BaseModel):
    """Pydantic schema for CommunityRuleBase."""
    rule: str


class CommunityRuleCreate(CommunityRuleBase):
    """Pydantic schema for CommunityRuleCreate."""
    pass


class CommunityRuleUpdate(CommunityRuleBase):
    """Pydantic schema for CommunityRuleUpdate."""
    pass


class CommunityRuleOut(CommunityRuleBase):
    """Pydantic schema for CommunityRuleOut."""
    id: int
    community_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommunityMemberBase(BaseModel):
    """Pydantic schema for CommunityMemberBase."""
    role: str  # Changed from Enum to str to avoid circular imports if Enum is moved
    activity_score: int


class CommunityMemberOut(CommunityMemberBase):
    """Pydantic schema for CommunityMemberOut."""
    user: "UserOut"
    join_date: datetime

    model_config = ConfigDict(from_attributes=True)


class CommunityOut(CommunityBase):
    """Pydantic schema for CommunityOut."""
    id: int
    created_at: datetime
    owner_id: int
    owner: "UserOut"
    member_count: int
    members: List["CommunityMemberOut"] = []
    rules: List["CommunityRuleOut"] = []
    category: Optional[Any] = None
    tags: List[Any] = Field(default_factory=list)
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class CommunityDetailOut(CommunityOut):
    """Detailed view of a community, can include extra fields if needed."""

    is_private: bool = False
    requires_approval: bool = False
    language: str = "en"

    model_config = ConfigDict(from_attributes=True)


class CommunityStatisticsBase(BaseModel):
    """Pydantic schema for CommunityStatisticsBase."""
    date: date
    member_count: int
    post_count: int
    comment_count: int
    active_users: int
    total_reactions: int
    average_posts_per_user: float


class CommunityStatisticsCreate(CommunityStatisticsBase):
    """Pydantic schema for CommunityStatisticsCreate."""
    pass


class CommunityStatistics(CommunityStatisticsBase):
    """Pydantic schema for CommunityStatistics."""
    id: int
    community_id: int

    model_config = ConfigDict(from_attributes=True)


class CommunityStatsOut(CommunityStatisticsBase):
    """Schema for outputting community statistics."""

    pass


class CommunityOverview(BaseModel):
    """Pydantic schema for CommunityOverview."""
    id: int
    name: str
    description: str
    member_count: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CommunityOverviewAnalytics(BaseModel):
    """Pydantic schema for CommunityOverviewAnalytics."""
    total_members: int
    active_members: int
    total_posts: int
    total_comments: int


class CommunityActivityAnalytics(BaseModel):
    """Pydantic schema for CommunityActivityAnalytics."""
    date: str
    posts: int
    comments: int
    active_users: int


class CommunityEngagementAnalytics(BaseModel):
    """Pydantic schema for CommunityEngagementAnalytics."""
    avg_likes_per_post: float
    avg_comments_per_post: float
    total_shares: int


class CommunityContentAnalysis(BaseModel):
    """Pydantic schema for CommunityContentAnalysis."""
    type: str
    count: int
    avg_engagement: float


class CommunityGrowthAnalytics(BaseModel):
    """Pydantic schema for CommunityGrowthAnalytics."""
    date: str
    members: int


class CommunityAnalytics(BaseModel):
    """Pydantic schema for CommunityAnalytics."""
    overview: CommunityOverviewAnalytics
    activity: List[CommunityActivityAnalytics]
    engagement: CommunityEngagementAnalytics
    content_analysis: List[CommunityContentAnalysis]
    growth: List[CommunityGrowthAnalytics]


class CommunityRole(str, Enum):
    """Pydantic schema for CommunityRole."""
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    VIP = "vip"
    MEMBER = "member"


class MemberRoleUpdate(BaseModel):
    """Pydantic schema for MemberRoleUpdate."""
    role: CommunityRole


class CommunityMemberCreate(CommunityMemberBase):
    """Pydantic schema for CommunityMemberCreate."""
    user_id: int


class CommunityMemberUpdate(CommunityMemberBase):
    """Pydantic schema for CommunityMemberUpdate."""
    pass


class CommunityInvitationBase(BaseModel):
    """Pydantic schema for CommunityInvitationBase."""
    community_id: int
    invitee_id: int


class CommunityInvitationCreate(CommunityInvitationBase):
    """Pydantic schema for CommunityInvitationCreate."""
    user_id: int  # Added for consistency with router usage


class CommunityInvitationOut(BaseModel):
    """Pydantic schema for CommunityInvitationOut."""
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
    """Pydantic schema for CommunityInvitationResponse."""
    accept: bool = Field(
        ...,
        description="Set to true to accept the invitation, false to decline it.",
    )


class CategoryBase(BaseModel):
    """Pydantic schema for CategoryBase."""
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    """Pydantic schema for CategoryCreate."""
    pass


class CategoryOut(CategoryCreate):
    """Pydantic schema for CategoryOut."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class Category(CategoryBase):
    """Pydantic schema for Category."""
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class TagBase(BaseModel):
    """Pydantic schema for TagBase."""
    name: str


class Tag(TagBase):
    """Pydantic schema for Tag."""
    id: int

    model_config = ConfigDict(from_attributes=True)


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
    "CommunityDetailOut",  # <--- Added
    "CommunitySettingsUpdate",  # <--- Added
    "MemberRoleUpdate",  # <--- Added
    "CommunityStatsOut",  # <--- Added
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
    "CategoryBase",
    "CategoryCreate",
    "CategoryOut",
    "Category",
    "TagBase",
    "Tag",
]
