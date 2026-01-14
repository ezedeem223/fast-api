"""Pydantic schemas for the collaboration domain."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .models import ProjectStatus


class ProjectCreate(BaseModel):
    """Pydantic schema for ProjectCreate."""
    title: str
    description: Optional[str] = None
    goals: Optional[str] = None
    community_id: Optional[int] = None


class ProjectOut(BaseModel):
    """Pydantic schema for ProjectOut."""
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
    """Pydantic schema for ContributionCreate."""
    content: Optional[str] = None
    contribution_type: str = "text"


class ContributionOut(BaseModel):
    """Pydantic schema for ContributionOut."""
    id: int
    project_id: int
    user_id: int
    content: Optional[str]
    contribution_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectWithContributions(ProjectOut):
    """Pydantic schema for ProjectWithContributions."""
    contributions: List[ContributionOut] = []
