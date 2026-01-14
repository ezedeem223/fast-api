"""Business logic for moderation workflows (warnings, bans, report handling)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.modules.moderation.models import AppealStatus, BlockAppeal
from app.modules.utils.analytics import update_ban_statistics

REPORT_THRESHOLD = 5  # Number of valid reports required for automatic ban
REPORT_WINDOW = timedelta(days=30)
WARNING_THRESHOLD = 3  # Escalate to ban after this many warnings


def _get_model_by_id(db: Session, model, id_value):
    """Helper for  get model by id."""
    instance = db.query(model).filter(model.id == id_value).first()
    if not instance:
        raise ValueError(f"{model.__name__} with id {id_value} not found")
    return instance


def _handle_errors(func):
    """Log and re-raise errors to preserve call-stack signal while adding diagnostics."""

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
    """Helper for warn user."""
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
    """Helper for ban user."""
    user = _get_model_by_id(db, models.User, user_id)

    user.ban_count += 1
    ban_duration = calculate_ban_duration(user.ban_count)
    user.current_ban_end = datetime.now(timezone.utc) + ban_duration
    user.total_ban_duration += ban_duration

    ban = models.UserBan(user_id=user_id, reason=reason, duration=ban_duration)
    db.add(ban)

    db.commit()
    update_ban_statistics(db, "user", reason, float(user.ban_count))


@_handle_errors
def unblock_user(db: Session, blocker_id: int, blocked_id: int) -> int:
    """Mark active blocks between two users as ended now."""
    now = datetime.now(timezone.utc)
    updated = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == blocker_id,
            models.Block.blocked_id == blocked_id,
            (models.Block.ends_at.is_(None) | (models.Block.ends_at > now)),
        )
        .update({"ends_at": now}, synchronize_session=False)
    )
    db.commit()
    if updated:
        update_ban_statistics(db, "user", "unblock", float(updated))
    return updated or 0


@_handle_errors
def clean_expired_blocks(db: Session) -> int:
    """Cleanup blocks whose ends_at has passed."""
    now = datetime.now(timezone.utc)
    expired = (
        db.query(models.Block)
        .filter(models.Block.ends_at.isnot(None), models.Block.ends_at <= now)
        .delete(synchronize_session=False)
    )
    db.commit()
    if expired:
        update_ban_statistics(db, "user", "clean_expired_blocks", float(expired))
    return expired or 0


def calculate_ban_duration(ban_count: int) -> timedelta:
    """Helper for calculate ban duration."""
    if ban_count == 1:
        return timedelta(days=1)
    if ban_count == 2:
        return timedelta(days=7)
    if ban_count == 3:
        return timedelta(days=30)
    return timedelta(days=365)


@_handle_errors
def process_report(db: Session, report_id: int, is_valid: bool, reviewer_id: int):
    """Helper for process report."""
    report = _get_model_by_id(db, models.Report, report_id)

    report.is_valid = is_valid
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewed_by = reviewer_id
    report.status = models.ReportStatus.REVIEWED

    reported_user = _get_model_by_id(db, models.User, report.reported_user_id)
    reported_user.total_reports += 1
    if is_valid:
        reported_user.valid_reports += 1

    db.commit()

    if is_valid:
        check_auto_ban(db, report.reported_user_id)


@_handle_errors
def resolve_report(
    db: Session,
    *,
    report_id: int,
    action: str,
    reviewer_id: int,
    resolution_notes: str | None = None,
) -> models.Report:
    """Helper for resolve report."""
    report = _get_model_by_id(db, models.Report, report_id)
    now = datetime.now(timezone.utc)

    if action == "delete":
        # Treat delete actions as valid reports and scrub the offending content.
        if report.post_id:
            post = _get_model_by_id(db, models.Post, report.post_id)
            post.is_deleted = True
            post.deleted_at = now
            post.title = "[Deleted]"
            post.content = "[Deleted]"
            if hasattr(post, "media_url"):
                post.media_url = None
            if hasattr(post, "media_text"):
                post.media_text = None
        elif report.comment_id:
            comment = _get_model_by_id(db, models.Comment, report.comment_id)
            comment.is_deleted = True
            comment.deleted_at = now
            comment.content = "[Deleted]"
        is_valid = True
    else:
        is_valid = False

    # Persist the moderator decision and update reporter metadata.
    report.resolution_notes = resolution_notes
    report.status = models.ReportStatus.RESOLVED
    report.reviewed_at = now
    report.reviewed_by = reviewer_id
    report.is_valid = is_valid

    reported_user = _get_model_by_id(db, models.User, report.reported_user_id)
    reported_user.total_reports += 1
    if is_valid:
        reported_user.valid_reports += 1

    db.commit()

    if is_valid:
        check_auto_ban(db, report.reported_user_id)

    db.refresh(report)
    return report


@_handle_errors
def unban_user(db: Session, user_id: int) -> models.User:
    """Helper for unban user."""
    user = _get_model_by_id(db, models.User, user_id)
    user.current_ban_end = None
    db.commit()
    db.refresh(user)
    return user


@_handle_errors
def check_auto_ban(db: Session, user_id: int):
    """Helper for check auto ban."""
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


@_handle_errors
def submit_block_appeal(
    db: Session, block_id: int, user_id: int, reason: str
) -> BlockAppeal:
    """Submit an appeal for a given block."""
    if not reason or not reason.strip():
        raise ValueError("Reason required")
    block = _get_model_by_id(db, models.Block, block_id)
    if block.blocked_id != user_id:
        raise ValueError("User is not the blocked party")
    appeal = BlockAppeal(block_id=block_id, user_id=user_id, reason=reason.strip())
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return appeal


@_handle_errors
def review_block_appeal(
    db: Session, appeal_id: int, approve: bool, reviewer_id: int
) -> BlockAppeal:
    """Helper for review block appeal."""
    appeal = _get_model_by_id(db, BlockAppeal, appeal_id)
    appeal.status = AppealStatus.APPROVED if approve else AppealStatus.REJECTED
    appeal.reviewed_at = datetime.now(timezone.utc)
    appeal.reviewer_id = reviewer_id
    db.commit()
    db.refresh(appeal)
    return appeal


__all__ = [
    "ban_user",
    "unblock_user",
    "clean_expired_blocks",
    "calculate_ban_duration",
    "check_auto_ban",
    "process_report",
    "resolve_report",
    "unban_user",
    "warn_user",
    "submit_block_appeal",
    "review_block_appeal",
]
