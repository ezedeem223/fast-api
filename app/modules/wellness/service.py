# app/modules/wellness/service.py

from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
from app.modules.wellness.models import (
    DigitalWellnessMetrics,
    WellnessAlert,
    WellnessSession,
    WellnessGoal,
    WellnessMode,
    WellnessLevel,
    UsagePattern,
)


class WellnessService:

    @staticmethod
    def get_or_create_metrics(db: Session, user_id: int) -> DigitalWellnessMetrics:
        """Fetch existing metrics or create a baseline record to avoid None checks in callers."""
        metrics = (
            db.query(DigitalWellnessMetrics)
            .filter(DigitalWellnessMetrics.user_id == user_id)
            .first()
        )

        if not metrics:
            metrics = DigitalWellnessMetrics(user_id=user_id)
            db.add(metrics)
            db.commit()
            db.refresh(metrics)

        return metrics

    @staticmethod
    def update_usage_metrics(db: Session, user_id: int, usage_minutes: int):
        if usage_minutes < 0:
            raise ValueError("usage_minutes cannot be negative")
        metrics = WellnessService.get_or_create_metrics(db, user_id)

        metrics.daily_usage_minutes = usage_minutes
        metrics.last_activity_at = datetime.now(timezone.utc)

        if usage_minutes < 60:
            metrics.usage_pattern = UsagePattern.LIGHT
        elif usage_minutes < 180:
            metrics.usage_pattern = UsagePattern.MODERATE
        elif usage_minutes < 360:
            metrics.usage_pattern = UsagePattern.HEAVY
        else:
            metrics.usage_pattern = UsagePattern.EXCESSIVE

        WellnessService._calculate_wellness_score(metrics)

        db.commit()
        return metrics

    @staticmethod
    def create_wellness_alert(
        db: Session,
        user_id: int,
        alert_type: str,
        severity: str,
        message: str,
        recommendation: Optional[str] = None,
    ) -> WellnessAlert:
        metrics = WellnessService.get_or_create_metrics(db, user_id)

        alert = WellnessAlert(
            metrics_id=metrics.id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            recommendation=recommendation,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def start_wellness_session(
        db: Session, user_id: int, session_type: str
    ) -> WellnessSession:
        metrics = WellnessService.get_or_create_metrics(db, user_id)

        session = WellnessSession(
            metrics_id=metrics.id, session_type=session_type, duration_minutes=0
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def end_wellness_session(db: Session, session_id: int):
        session = (
            db.query(WellnessSession).filter(WellnessSession.id == session_id).first()
        )

        if session:
            session.ended_at = datetime.now(timezone.utc)
            duration = (session.ended_at - session.started_at).total_seconds() / 60
            session.duration_minutes = int(duration)

            db.commit()

            return session

        logging.getLogger(__name__).error("Wellness session not found: %s", session_id)
        return None

    @staticmethod
    def set_wellness_goal(
        db: Session,
        user_id: int,
        goal_type: str,
        target_value: float,
        target_date: Optional[datetime] = None,
    ) -> WellnessGoal:
        metrics = WellnessService.get_or_create_metrics(db, user_id)

        goal = WellnessGoal(
            metrics_id=metrics.id,
            goal_type=goal_type,
            target_value=target_value,
            target_date=target_date,
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def enable_do_not_disturb(db: Session, user_id: int, duration_minutes: int):
        mode = db.query(WellnessMode).filter(WellnessMode.user_id == user_id).first()

        if not mode:
            mode = WellnessMode(user_id=user_id)
            db.add(mode)

        mode.do_not_disturb = True
        mode.do_not_disturb_until = datetime.now(timezone.utc) + timedelta(
            minutes=duration_minutes
        )

        db.commit()
        if mode.do_not_disturb_until and mode.do_not_disturb_until.tzinfo is None:
            mode.do_not_disturb_until = mode.do_not_disturb_until.replace(
                tzinfo=timezone.utc
            )
        return mode

    @staticmethod
    def enable_mental_health_mode(db: Session, user_id: int, duration_minutes: int):
        mode = db.query(WellnessMode).filter(WellnessMode.user_id == user_id).first()

        if not mode:
            mode = WellnessMode(user_id=user_id)
            db.add(mode)

        mode.mental_health_mode = True
        mode.mental_health_mode_until = datetime.now(timezone.utc) + timedelta(
            minutes=duration_minutes
        )

        db.commit()
        if mode.mental_health_mode_until and mode.mental_health_mode_until.tzinfo is None:
            mode.mental_health_mode_until = mode.mental_health_mode_until.replace(
                tzinfo=timezone.utc
            )
        return mode

    @staticmethod
    def _calculate_wellness_score(metrics: DigitalWellnessMetrics):
        score = 100.0

        if metrics.daily_usage_minutes > 360:
            score -= (metrics.daily_usage_minutes - 360) * 0.1

        score -= metrics.stress_level * 5

        score -= metrics.anxiety_level * 3

        score += (metrics.mood_score - 5) * 5

        score -= metrics.digital_fatigue * 0.5

        score -= metrics.comparison_anxiety * 0.3

        metrics.wellness_score = max(0, min(100, score))

        if metrics.wellness_score >= 80:
            metrics.wellness_level = WellnessLevel.EXCELLENT
        elif metrics.wellness_score >= 60:
            metrics.wellness_level = WellnessLevel.GOOD
        elif metrics.wellness_score >= 40:
            metrics.wellness_level = WellnessLevel.FAIR
        elif metrics.wellness_score >= 20:
            metrics.wellness_level = WellnessLevel.POOR
        else:
            metrics.wellness_level = WellnessLevel.CRITICAL
