"""Reporting utilities for abuse reports and auto-expiry of ban statistics."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.modules.users.models import User
from app.modules.utils.content import is_content_offensive
from fastapi import HTTPException

REPORTS_DAILY_LIMIT = 3


def _ensure_reason(reason: Optional[str]) -> str:
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="A report reason must be provided")
    return reason.strip()


def submit_report(
    db: Session,
    current_user: User,
    *,
    reason: Optional[str],
    post_id: Optional[int] = None,
    comment_id: Optional[int] = None,
) -> dict:
    if getattr(current_user, "is_suspended", False):
        raise HTTPException(
            status_code=403, detail="Suspended users cannot submit reports"
        )

    recent_window = datetime.now(timezone.utc) - timedelta(days=1)
    recent_count = (
        db.query(models.Report)
        .filter(
            models.Report.reporter_id == current_user.id,
            models.Report.created_at >= recent_window,
        )
        .count()
    )
    if recent_count >= REPORTS_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Report limit reached")

    reason_text = _ensure_reason(reason)

    if (post_id is None and comment_id is None) or (
        post_id is not None and comment_id is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide either post_id or comment_id to submit a report",
        )

    # Prevent duplicate report by same user on same target
    dup_filters = [models.Report.reporter_id == current_user.id]
    if post_id is not None:
        dup_filters.append(models.Report.post_id == post_id)
    if comment_id is not None:
        dup_filters.append(models.Report.comment_id == comment_id)
    existing = db.query(models.Report).filter(*dup_filters).first()
    if existing:
        raise HTTPException(status_code=409, detail="Report already submitted")

    if post_id is not None:
        target = db.query(models.Post).filter(models.Post.id == post_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Post not found")

        report = models.Report(
            post_id=post_id,
            reported_user_id=target.owner_id,
            reporter_id=current_user.id,
            report_reason=reason_text,
        )

        is_offensive, confidence = is_content_offensive(target.content or "")
        report.ai_detected = is_offensive
        report.ai_confidence = confidence

        if is_offensive and not target.is_flagged:
            target.is_flagged = True
            target.flag_reason = (
                f"AI detected offensive content (confidence: {confidence:.2f})"
            )
            target.is_safe_content = False

    else:
        target = (
            db.query(models.Comment).filter(models.Comment.id == comment_id).first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="Comment not found")

        report = models.Report(
            comment_id=comment_id,
            reported_user_id=target.owner_id,
            reporter_id=current_user.id,
            report_reason=reason_text,
        )

        is_offensive, confidence = is_content_offensive(target.content or "")
        report.ai_detected = is_offensive
        report.ai_confidence = confidence

        if is_offensive and not target.is_flagged:
            target.is_flagged = True
            target.flag_reason = (
                f"AI detected offensive comment (confidence: {confidence:.2f})"
            )

    report.created_at = getattr(report, "created_at", datetime.now(timezone.utc))
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"message": "Report submitted successfully"}
