import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.modules.utils.moderation import log_admin_action
from app.services.reporting import submit_report
from app.services.support_service import SupportService
from fastapi import HTTPException


def test_support_ticket_create_and_update(session):
    user = models.User(email="sup28@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    svc = SupportService(session)
    ticket = svc.create_ticket(
        current_user=user,
        subject="Help needed",
        description="Issue description",
    )
    assert ticket.status == models.TicketStatus.OPEN

    svc.add_response(current_user=user, ticket_id=ticket.id, content="Follow-up")
    updated = svc.update_ticket_status(ticket.id, models.TicketStatus.CLOSED)
    assert updated.status == models.TicketStatus.CLOSED
    assert len(updated.responses) == 1


def test_report_submission(session):
    reporter = models.User(
        email="rep28@example.com", hashed_password="x", is_verified=True
    )
    session.add(reporter)
    session.commit()
    session.refresh(reporter)

    post = models.Post(owner_id=reporter.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    svc = SupportService(session)
    report = svc.submit_report(
        reporter_id=reporter.id, reason="spam", post_id=post.id, comment_id=None
    )
    assert report.reason == "spam"
    assert report.reporter_id == reporter.id


def test_report_duplicate_blocked_and_invalid_target(session):
    user = models.User(
        email="rep28b@example.com", hashed_password="x", is_verified=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    post = models.Post(owner_id=user.id, title="t", content="c")
    session.add(post)
    session.commit()

    # first report ok
    submit_report(session, user, reason="spam", post_id=post.id, comment_id=None)
    # duplicate raises 409
    with pytest.raises(HTTPException) as exc:
        submit_report(session, user, reason="spam", post_id=post.id, comment_id=None)
    assert exc.value.status_code == 409

    # invalid target raises 404
    with pytest.raises(HTTPException) as exc2:
        submit_report(session, user, reason="bad", post_id=9999, comment_id=None)
    assert exc2.value.status_code == 404


def test_audit_logging_record_filter_and_export(session):
    # record multiple actions
    now = datetime.now(timezone.utc)
    log_admin_action(session, admin_id=1, action="a1", metadata={"k": "v"})
    log_admin_action(session, admin_id=2, action="a2", metadata={"x": "y"})

    logs = session.query(models.AuditLog).all()
    assert len(logs) >= 2

    # filter by admin_id
    admin1_logs = (
        session.query(models.AuditLog).filter(models.AuditLog.admin_id == 1).all()
    )
    assert all(log.admin_id == 1 for log in admin1_logs)

    # filter by date window
    recent_logs = (
        session.query(models.AuditLog)
        .filter(models.AuditLog.created_at >= now - timedelta(minutes=5))
        .all()
    )
    assert recent_logs

    # export to CSV/JSON
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=["admin_id", "action"])
    writer.writeheader()
    for log in logs:
        writer.writerow({"admin_id": log.admin_id, "action": log.action})
    csv_val = csv_buf.getvalue()
    assert "admin_id" in csv_val and "action" in csv_val

    json_payload = json.dumps(
        [{"admin_id": log.admin_id, "action": log.action} for log in logs]
    )
    parsed = json.loads(json_payload)
    assert parsed[0]["action"]
