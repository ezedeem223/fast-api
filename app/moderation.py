from datetime import datetime, timedelta, timezone  # Added timezone for consistency
from sqlalchemy.orm import Session
from . import models, schemas
from sqlalchemy import func

# Constants for automatic ban configuration
REPORT_THRESHOLD = 5  # Number of valid reports required for automatic ban
REPORT_WINDOW = timedelta(days=30)  # Time window to consider reports

# You may also define a constant for warning threshold (e.g., 3 warnings)
WARNING_THRESHOLD = 3


def warn_user(db: Session, user_id: int, reason: str):
    """
    Warn a user by increasing their warning count and recording the warning date.
    If warnings exceed the threshold, automatically ban the user.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    # Update warning count and last warning date using UTC for consistency
    user.warning_count += 1
    user.last_warning_date = datetime.now(timezone.utc)

    if user.warning_count >= WARNING_THRESHOLD:
        ban_user(db, user_id, reason)
    else:
        # Create a warning record in the database
        warning = models.UserWarning(user_id=user_id, reason=reason)
        db.add(warning)

    db.commit()


def ban_user(db: Session, user_id: int, reason: str):
    """
    Ban a user by increasing their ban count, calculating ban duration,
    updating ban end time, and recording the ban in the database.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    user.ban_count += 1
    ban_duration = calculate_ban_duration(user.ban_count)
    user.current_ban_end = datetime.now(timezone.utc) + ban_duration
    user.total_ban_duration += ban_duration

    # Create a ban record in the database
    ban = models.UserBan(user_id=user_id, reason=reason, duration=ban_duration)
    db.add(ban)

    db.commit()


def calculate_ban_duration(ban_count: int) -> timedelta:
    """
    Calculate the ban duration based on the number of times a user has been banned.
    Returns a timedelta representing the duration.
    """
    if ban_count == 1:
        return timedelta(days=1)
    elif ban_count == 2:
        return timedelta(days=7)
    elif ban_count == 3:
        return timedelta(days=30)
    else:
        return timedelta(days=365)  # One year ban for repeated offenses


def process_report(db: Session, report_id: int, is_valid: bool, reviewer_id: int):
    """
    Process a user report by updating its status and review details.
    Also, update the reported user's report counts and check for auto-ban if the report is valid.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise ValueError("Report not found")

    report.is_valid = is_valid
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewed_by = reviewer_id

    reported_user = (
        db.query(models.User).filter(models.User.id == report.reported_user_id).first()
    )
    if not reported_user:
        raise ValueError("Reported user not found")

    reported_user.total_reports += 1
    if is_valid:
        reported_user.valid_reports += 1

    db.commit()

    if is_valid:
        check_auto_ban(db, report.reported_user_id)


def check_auto_ban(db: Session, user_id: int):
    """
    Check if a user should be automatically banned based on the number of valid reports
    received within a specified time window.
    """
    valid_reports_count = (
        db.query(func.count(models.Report.id))
        .filter(
            models.Report.reported_user_id == user_id,
            models.Report.is_valid == True,
            models.Report.created_at >= datetime.now(timezone.utc) - REPORT_WINDOW,
        )
        .scalar()
    )

    if valid_reports_count >= REPORT_THRESHOLD:
        ban_user(db, user_id, "Automatic ban due to multiple valid reports")
