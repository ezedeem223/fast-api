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
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class WellnessLevel(str, enum.Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class UsagePattern(str, enum.Enum):
    LIGHT = "light"  # أقل من ساعة يومياً
    MODERATE = "moderate"  # 1-3 ساعات يومياً
    HEAVY = "heavy"  # 3-6 ساعات يومياً
    EXCESSIVE = "excessive"  # أكثر من 6 ساعات يومياً


class DigitalWellnessMetrics(Base):
    """نموذج مؤشرات الصحة الرقمية"""

    __tablename__ = "digital_wellness_metrics"

    id = Column(Integer, primary_key=True)

    # المستخدم
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # مؤشرات الصحة
    wellness_score = Column(Float, default=100.0)  # من 0 إلى 100
    wellness_level = Column(Enum(WellnessLevel), default=WellnessLevel.EXCELLENT)

    # الاستخدام
    daily_usage_minutes = Column(Integer, default=0)  # دقائق الاستخدام اليومي
    weekly_usage_hours = Column(Float, default=0.0)  # ساعات الاستخدام الأسبوعي
    usage_pattern = Column(Enum(UsagePattern), default=UsagePattern.LIGHT)

    # الأنشطة
    posts_per_day = Column(Float, default=0.0)
    comments_per_day = Column(Float, default=0.0)
    likes_received_per_day = Column(Float, default=0.0)

    # المؤشرات النفسية
    stress_level = Column(Float, default=0.0)  # من 0 إلى 10
    anxiety_level = Column(Float, default=0.0)  # من 0 إلى 10
    mood_score = Column(Float, default=5.0)  # من 1 إلى 10

    # الإجهاد الرقمي
    digital_fatigue = Column(Float, default=0.0)  # من 0 إلى 100
    notification_overload = Column(Float, default=0.0)  # من 0 إلى 100
    comparison_anxiety = Column(Float, default=0.0)  # من 0 إلى 100

    # الأوقات
    last_break_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    # العلاقات
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
    """نموذج تنبيهات الصحة الرقمية"""

    __tablename__ = "wellness_alerts"

    id = Column(Integer, primary_key=True)

    # المرجع
    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    # التنبيه
    alert_type = Column(
        String, nullable=False
    )  # "excessive_usage", "stress_high", "mood_low"
    severity = Column(String, nullable=False)  # "low", "medium", "high"
    message = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)

    # الحالة
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    # الأوقات
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # العلاقات
    metrics = relationship("DigitalWellnessMetrics", back_populates="alerts")


class WellnessSession(Base):
    """نموذج جلسات الصحة الرقمية"""

    __tablename__ = "wellness_sessions"

    id = Column(Integer, primary_key=True)

    # المرجع
    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    # الجلسة
    session_type = Column(
        String, nullable=False
    )  # "break", "meditation", "offline_time"
    duration_minutes = Column(Integer, nullable=False)

    # الأوقات
    started_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # العلاقات
    metrics = relationship("DigitalWellnessMetrics", back_populates="sessions")


class WellnessGoal(Base):
    """نموذج أهداف الصحة الرقمية"""

    __tablename__ = "wellness_goals"

    id = Column(Integer, primary_key=True)

    # المرجع
    metrics_id = Column(
        Integer, ForeignKey("digital_wellness_metrics.id"), nullable=False, index=True
    )

    # الهدف
    goal_type = Column(
        String, nullable=False
    )  # "reduce_usage", "improve_mood", "reduce_stress"
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, default=0.0)

    # الحالة
    is_completed = Column(Boolean, default=False)
    progress_percentage = Column(Float, default=0.0)

    # الأوقات
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    target_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # العلاقات
    metrics = relationship("DigitalWellnessMetrics", back_populates="goals")


class WellnessMode(Base):
    """نموذج أوضاع الصحة الرقمية"""

    __tablename__ = "wellness_modes"

    id = Column(Integer, primary_key=True)

    # المستخدم
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # الأوضاع
    do_not_disturb = Column(Boolean, default=False)
    mental_health_mode = Column(Boolean, default=False)
    focus_mode = Column(Boolean, default=False)
    offline_mode = Column(Boolean, default=False)

    # الإعدادات
    do_not_disturb_until = Column(DateTime(timezone=True), nullable=True)
    mental_health_mode_until = Column(DateTime(timezone=True), nullable=True)
    focus_mode_until = Column(DateTime(timezone=True), nullable=True)

    # الأوقات
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    # العلاقات
    user = relationship("User")
