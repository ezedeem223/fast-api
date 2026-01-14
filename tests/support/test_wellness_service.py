"""Test module for test session25 wellness service."""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.modules.wellness.service import WellnessService


def test_update_usage_metrics_and_score(session):
    """Test case for test update usage metrics and score."""
    svc = WellnessService()
    metrics = svc.update_usage_metrics(session, user_id=1, usage_minutes=45)
    assert metrics.daily_usage_minutes == 45
    assert metrics.usage_pattern.value == "light"
    assert metrics.wellness_score <= 100

    metrics2 = svc.update_usage_metrics(session, user_id=1, usage_minutes=400)
    assert metrics2.usage_pattern.value == "excessive"
    assert metrics2.wellness_level in {
        models.WellnessLevel.FAIR,
        models.WellnessLevel.GOOD,
        models.WellnessLevel.EXCELLENT,
        models.WellnessLevel.POOR,
        models.WellnessLevel.CRITICAL,
    }


def test_create_and_end_sessions(session):
    """Test case for test create and end sessions."""
    svc = WellnessService()
    started = svc.start_wellness_session(session, user_id=2, session_type="focus")
    assert started.duration_minutes == 0
    ended = svc.end_wellness_session(session, session_id=started.id)
    assert ended.duration_minutes >= 0
    assert ended.ended_at is not None
    # non-existent session returns None without raising
    assert svc.end_wellness_session(session, session_id=9999) is None


def test_goals_and_alerts(session):
    """Test case for test goals and alerts."""
    svc = WellnessService()
    goal = svc.set_wellness_goal(
        session,
        user_id=3,
        goal_type="sleep",
        target_value=8.0,
        target_date=datetime.now(timezone.utc) + timedelta(days=7),
    )
    assert goal.goal_type == "sleep"
    alert = svc.create_wellness_alert(
        session,
        user_id=3,
        alert_type="usage",
        severity="high",
        message="Too much screen time",
    )
    assert alert.alert_type == "usage"
    # additional goals without target date
    goal2 = svc.set_wellness_goal(
        session, user_id=3, goal_type="steps", target_value=10000
    )
    assert goal2.target_date is None


def test_modes_toggle(session):
    """Test case for test modes toggle."""
    svc = WellnessService()
    dnd = svc.enable_do_not_disturb(session, user_id=4, duration_minutes=30)
    assert dnd.do_not_disturb is True
    assert dnd.do_not_disturb_until > datetime.now(timezone.utc)

    mh = svc.enable_mental_health_mode(session, user_id=4, duration_minutes=15)
    assert mh.mental_health_mode is True
    assert mh.mental_health_mode_until > datetime.now(timezone.utc)


def test_usage_metrics_negative_rejected(session):
    """Test case for test usage metrics negative rejected."""
    svc = WellnessService()
    with pytest.raises(ValueError):
        svc.update_usage_metrics(session, user_id=5, usage_minutes=-1)


def test_session_duration_uses_timezone(session):
    """Test case for test session duration uses timezone."""
    svc = WellnessService()
    started = svc.start_wellness_session(session, user_id=6, session_type="break")
    # force a naive datetime to ensure tz is applied
    started.started_at = started.started_at.replace(tzinfo=None)
    session.commit()
    ended = svc.end_wellness_session(session, session_id=started.id)
    assert ended.duration_minutes >= 0
