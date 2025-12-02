from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from .models import ProjectStatus


class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    goals: Optional[str] = None
    community_id: Optional[int] = None


class ProjectOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    goals: Optional[str]
    owner_id: int
    community_id: Optional[int]
    status: ProjectStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContributionCreate(BaseModel):
    content: Optional[str] = None
    contribution_type: str = "text"


class ContributionOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    content: Optional[str]
    contribution_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectWithContributions(ProjectOut):
    contributions: List[ContributionOut] = []
