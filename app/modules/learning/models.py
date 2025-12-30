# app/modules/learning/models.py - Learning paths and certification models

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class LearningPath(Base):
    """A curated learning path with modules and enrollments."""

    __tablename__ = "learning_paths"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    difficulty_level = Column(String, nullable=False)

    enrollments_count = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    modules = relationship("LearningModule", back_populates="path")
    enrollments = relationship("LearningEnrollment", back_populates="path")


class LearningModule(Base):
    """Individual module within a learning path."""

    __tablename__ = "learning_modules"

    id = Column(Integer, primary_key=True)
    path_id = Column(
        Integer, ForeignKey("learning_paths.id"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    order = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    path = relationship("LearningPath", back_populates="modules")


class LearningEnrollment(Base):
    """Enrollment progress for a learning path."""

    __tablename__ = "learning_enrollments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    path_id = Column(
        Integer, ForeignKey("learning_paths.id"), nullable=False, index=True
    )

    progress_percentage = Column(Float, default=0.0)
    is_completed = Column(Boolean, default=False)

    enrolled_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    path = relationship("LearningPath", back_populates="enrollments")


class Certificate(Base):
    """Certificate issued upon completion of a learning path."""

    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    path_id = Column(
        Integer, ForeignKey("learning_paths.id"), nullable=False, index=True
    )

    certificate_number = Column(String, unique=True, nullable=False)
    issued_by = Column(String, nullable=False)

    issued_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    path = relationship("LearningPath")


__all__ = ["LearningPath", "LearningModule", "LearningEnrollment", "Certificate"]
