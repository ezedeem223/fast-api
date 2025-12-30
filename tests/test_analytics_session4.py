from datetime import datetime, timedelta, timezone

import pytest

import app.analytics as analytics
from app import models


def test_log_analysis_event_success_and_failure(caplog):
    caplog.set_level("INFO")
    analytics.log_analysis_event(True, {"foo": "bar"})
    assert any("analytics.success" in rec.message for rec in caplog.records)

    caplog.clear()
    analytics.log_analysis_event(False, {"ctx": "value"}, RuntimeError("boom"))
    assert any("analytics.failure" in rec.message for rec in caplog.records)
    assert any(getattr(rec, "error", None) == "boom" for rec in caplog.records)

    # non-dict context should not raise
    analytics.log_analysis_event(False, "not-a-dict", "err")


def test_get_user_activity_filters_by_window(session):
    user = models.User(email="activity@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    user_id = user.id
    old_event = models.UserEvent(
        user_id=user_id,
        event_type="login",
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    new_event = models.UserEvent(
        user_id=user_id,
        event_type="post",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    other_user = models.User(email="other@example.com", hashed_password="x")
    other_event = models.UserEvent(
        user=other_user,
        event_type="post",
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([old_event, new_event, other_user, other_event])
    session.commit()

    activity = analytics.get_user_activity(session, user_id, days=30)
    assert activity == {"post": 1}


def test_get_problematic_users_threshold_and_window(session):
    # Create two users and valid/invalid reports
    reported = models.User(email="reported@example.com", hashed_password="x")
    reporter = models.User(email="reporter@example.com", hashed_password="x")
    other_reported = models.User(email="other@example.com", hashed_password="x")
    session.add_all([reported, reporter, other_reported])
    session.commit()

    recent_valid = [
        models.Report(
            report_reason="spam",
            reporter_id=reporter.id,
            reported_user_id=reported.id,
            is_valid=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        for _ in range(5)
    ]
    old_valid = models.Report(
        report_reason="abuse",
        reporter_id=reporter.id,
        reported_user_id=reported.id,
        is_valid=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    invalid_report = models.Report(
        report_reason="ignore",
        reporter_id=reporter.id,
        reported_user_id=other_reported.id,
        is_valid=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all(recent_valid + [old_valid, invalid_report])
    session.commit()

    flagged = analytics.get_problematic_users(session, threshold=5)
    assert len(flagged) == 1
    assert flagged[0].id == reported.id
