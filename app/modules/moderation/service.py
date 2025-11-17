"""Business logic for moderation workflows (warnings, bans, report handling)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.modules.moderation import schemas

REPORT_THRESHOLD = 5  # Number of valid reports required for automatic ban
REPORT_WINDOW = timedelta(days=30)
WARNING_THRESHOLD = 3


def _get_model_by_id(db: Session, model, id_value):
    instance = db.query(model).filter(model.id == id_value).first()
    if not instance:
        raise ValueError(f"{model.__name__} with id {id_value} not found")
    return instance


def _handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - logging only
            import logging

            logger = logging.getLogger(__name__)
            logger.error("Error in %s: %s", func.__name__, exc)
            raise

    return wrapper


@_handle_errors
def warn_user(db: Session, user_id: int, reason: str):
    user = _get_model_by_id(db, models.User, user_id)
    user.warning_count += 1
    user.last_warning_date = datetime.now(timezone.utc)

    if user.warning_count >= WARNING_THRESHOLD:
        ban_user(db, user_id, reason)
    else:
        warning = models.UserWarning(user_id=user_id, reason=reason)
        db.add(warning)

    db.commit()


@_handle_errors
def ban_user(db: Session, user_id: int, reason: str):
    user = _get_model_by_id(db, models.User, user_id)

    user.ban_count += 1
    ban_duration = calculate_ban_duration(user.ban_count)
    user.current_ban_end = datetime.now(timezone.utc) + ban_duration
    user.total_ban_duration += ban_duration

    ban = models.UserBan(user_id=user_id, reason=reason, duration=ban_duration)
    db.add(ban)

    db.commit()


def calculate_ban_duration(ban_count: int) -> timedelta:
    if ban_count == 1:
        return timedelta(days=1)
    if ban_count == 2:
        return timedelta(days=7)
    if ban_count == 3:
        return timedelta(days=30)
    return timedelta(days=365)


@_handle_errors
def process_report(db: Session, report_id: int, is_valid: bool, reviewer_id: int):
    report = _get_model_by_id(db, models.Report, report_id)

    report.is_valid = is_valid
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewed_by = reviewer_id

    reported_user = _get_model_by_id(db, models.User, report.reported_user_id)
    reported_user.total_reports += 1
    if is_valid:
        reported_user.valid_reports += 1

    db.commit()

    if is_valid:
        check_auto_ban(db, report.reported_user_id)


@_handle_errors
def check_auto_ban(db: Session, user_id: int):
    valid_reports_count = (
        db.query(func.count(models.Report.id))
        .filter(
            models.Report.reported_user_id == user_id,
            models.Report.is_valid.is_(True),
            models.Report.created_at >= datetime.now(timezone.utc) - REPORT_WINDOW,
        )
        .scalar()
    )

    if valid_reports_count >= REPORT_THRESHOLD:
        ban_user(db, user_id, "Automatic ban due to multiple valid reports")


__all__ = [
    "ban_user",
    "calculate_ban_duration",
    "check_auto_ban",
    "process_report",
    "warn_user",
]
