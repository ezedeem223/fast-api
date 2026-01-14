"""Wellness router for metrics, alerts, sessions, modes, and goals.

Auth required; delegates to WellnessService for persistence and calculations. Exposes
endpoints for metrics ingestion, goal management, alerts, mode toggles, and summary.
"""

from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.users.models import User
from app.modules.wellness.service import WellnessService
from app.oauth2 import get_current_user
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/wellness", tags=["Wellness"])


class WellnessGoalRequest(BaseModel):
    """Class WellnessGoalRequest."""
    goal_type: str
    target_value: float
    target_date: Optional[str] = None


class DoNotDisturbRequest(BaseModel):
    """Class DoNotDisturbRequest."""
    duration_minutes: int


@router.get("/metrics")
async def get_wellness_metrics(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Return current wellness metrics for the authenticated user."""
    metrics = WellnessService.get_or_create_metrics(db, current_user.id)
    return {
        "wellness_score": metrics.wellness_score,
        "wellness_level": metrics.wellness_level,
        "daily_usage_minutes": metrics.daily_usage_minutes,
        "usage_pattern": metrics.usage_pattern,
        "stress_level": metrics.stress_level,
        "mood_score": metrics.mood_score,
        "digital_fatigue": metrics.digital_fatigue,
    }


@router.post("/goals")
async def create_wellness_goal(
    request: WellnessGoalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create wellness goal."""
    """ """
    goal = WellnessService.set_wellness_goal(
        db=db,
        user_id=current_user.id,
        goal_type=request.goal_type,
        target_value=request.target_value,
    )
    return {"id": goal.id, "goal_type": goal.goal_type}


@router.post("/do-not-disturb")
async def enable_do_not_disturb(
    request: DoNotDisturbRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Helper for enable do not disturb."""
    """ """
    mode = WellnessService.enable_do_not_disturb(
        db=db, user_id=current_user.id, duration_minutes=request.duration_minutes
    )
    return {"do_not_disturb": mode.do_not_disturb}


@router.post("/mental-health-mode")
async def enable_mental_health_mode(
    request: DoNotDisturbRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Helper for enable mental health mode."""
    """ """
    mode = WellnessService.enable_mental_health_mode(
        db=db, user_id=current_user.id, duration_minutes=request.duration_minutes
    )
    return {"mental_health_mode": mode.mental_health_mode}
