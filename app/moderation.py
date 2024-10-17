from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from . import models, schemas
from sqlalchemy import func


REPORT_THRESHOLD = 5  # عدد البلاغات الصحيحة قبل الحظر التلقائي
REPORT_WINDOW = timedelta(days=30)  # فترة زمنية للنظر في البلاغات


def warn_user(db: Session, user_id: int, reason: str):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    user.warning_count += 1
    user.last_warning_date = datetime.now()

    if user.warning_count >= 3:
        ban_user(db, user_id, reason)
    else:
        # إنشاء سجل تحذير
        warning = models.UserWarning(user_id=user_id, reason=reason)
        db.add(warning)

    db.commit()


def ban_user(db: Session, user_id: int, reason: str):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    user.ban_count += 1
    ban_duration = calculate_ban_duration(user.ban_count)
    user.current_ban_end = datetime.now() + ban_duration
    user.total_ban_duration += ban_duration

    # إنشاء سجل حظر
    ban = models.UserBan(user_id=user_id, reason=reason, duration=ban_duration)
    db.add(ban)

    db.commit()


def calculate_ban_duration(ban_count: int) -> timedelta:
    if ban_count == 1:
        return timedelta(days=1)
    elif ban_count == 2:
        return timedelta(days=7)
    elif ban_count == 3:
        return timedelta(days=30)
    else:
        return timedelta(days=365)  # حظر لمدة سنة للمخالفات المتكررة


def process_report(db: Session, report_id: int, is_valid: bool, reviewer_id: int):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise ValueError("Report not found")

    report.is_valid = is_valid
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewed_by = reviewer_id
    reported_user = (
        db.query(models.User).filter(models.User.id == report.reported_user_id).first()
    )
    reported_user.total_reports += 1
    if is_valid:
        reported_user.valid_reports += 1

    db.commit()

    if is_valid:
        check_auto_ban(db, report.reported_user_id)


def check_auto_ban(db: Session, user_id: int):
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
