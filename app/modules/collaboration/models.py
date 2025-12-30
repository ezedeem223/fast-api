"""Collaboration domain models."""

import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default


class ProjectStatus(str, enum.Enum):
    IDEA = "idea"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CollaborativeProject(Base):
    """Represents a co-creation project or workshop."""

    __tablename__ = "collaborative_projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    goals = Column(Text, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    community_id = Column(
        Integer, ForeignKey("communities.id", ondelete="SET NULL"), nullable=True
    )

    status = Column(Enum(ProjectStatus), default=ProjectStatus.IDEA)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    # Intellectual Property License (Creative Commons, etc.)
    license_type = Column(String, default="CC-BY")

    owner = relationship("User", backref="owned_projects")
    contributions = relationship("ProjectContribution", back_populates="project")


class ProjectContribution(Base):
    """Tracks individual contributions to a project."""

    __tablename__ = "project_contributions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("collaborative_projects.id", ondelete="CASCADE")
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    content = Column(Text, nullable=True)
    contribution_type = Column(String, default="text")  # code, design, text
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    project = relationship("CollaborativeProject", back_populates="contributions")
    user = relationship("User", backref="project_contributions")


__all__ = ["CollaborativeProject", "ProjectContribution", "ProjectStatus"]
