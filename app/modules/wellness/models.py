"""SQLAlchemy models for the wellness domain."""
# app/modules/wellness/models.py

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class WellnessLevel(str, enum.Enum):
    """SQLAlchemy model for WellnessLevel."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class UsagePattern(str, enum.Enum):
    """SQLAlchemy model for UsagePattern."""
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    EXCESSIVE = "excessive"


class DigitalWellnessMetrics(Base):

    """SQLAlchemy model for DigitalWellnessMetrics."""
    __tablename__ = "digital_wellness_metrics"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    wellness_score = Column(Float, default=100.0)
    wellness_level = Column(Enum(WellnessLevel), default=WellnessLevel.EXCELLENT)

    # Activity usage aggregates used to derive usage patterns.
    daily_usage_minutes = Column(Integer, default=0)
    weekly_usage_hours = Column(Float, default=0.0)
    usage_pattern = Column(Enum(UsagePattern), default=UsagePattern.LIGHT)

    # Engagement signals used in wellness scoring.
    posts_per_day = Column(Float, default=0.0)
    comments_per_day = Column(Float, default=0.0)
    likes_received_per_day = Column(Float, default=0.0)

    # Self-reported or inferred mental state indicators.
    stress_level = Column(Float, default=0.0)
    anxiety_level = Column(Float, default=0.0)
    mood_score = Column(Float, default=5.0)

    digital_fatigue = Column(Float, default=0.0)
    notification_overload = Column(Float, default=0.0)
    comparison_anxiety = Column(Float, default=0.0)

    last_break_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    user = relationship("User")
    alerts = relationship(
        "WellnessAlert", back_populates="metrics", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "WellnessSession", back_populates="metrics", cascade="all, delete-orphan"
    )
    goals = relationship(
        "WellnessGoal", back_populates="metrics", cascade="all, delete-orphan"
    )


class WellnessAlert(Base):

    """SQLAlchemy model for WellnessAlert."""
    __tablename__ = "wellness_alerts"

    id = Column(Integer, primary_key=True)

    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    alert_type = Column(
        String, nullable=False
    )  # "excessive_usage", "stress_high", "mood_low"
    severity = Column(String, nullable=False)  # "low", "medium", "high"
    message = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)

    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    metrics = relationship("DigitalWellnessMetrics", back_populates="alerts")


class WellnessSession(Base):

    """SQLAlchemy model for WellnessSession."""
    __tablename__ = "wellness_sessions"

    id = Column(Integer, primary_key=True)

    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    session_type = Column(
        String, nullable=False
    )  # "break", "meditation", "offline_time"
    duration_minutes = Column(Integer, nullable=False)

    started_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    metrics = relationship("DigitalWellnessMetrics", back_populates="sessions")


class WellnessGoal(Base):

    """SQLAlchemy model for WellnessGoal."""
    __tablename__ = "wellness_goals"

    id = Column(Integer, primary_key=True)

    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    goal_type = Column(
        String, nullable=False
    )  # "reduce_usage", "improve_mood", "reduce_stress"
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, default=0.0)

    is_completed = Column(Boolean, default=False)
    progress_percentage = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    target_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    metrics = relationship("DigitalWellnessMetrics", back_populates="goals")


class WellnessMode(Base):

    """SQLAlchemy model for WellnessMode."""
    __tablename__ = "wellness_modes"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    do_not_disturb = Column(Boolean, default=False)
    mental_health_mode = Column(Boolean, default=False)
    focus_mode = Column(Boolean, default=False)
    offline_mode = Column(Boolean, default=False)

    do_not_disturb_until = Column(DateTime(timezone=True), nullable=True)
    mental_health_mode_until = Column(DateTime(timezone=True), nullable=True)
    focus_mode_until = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    user = relationship("User")
