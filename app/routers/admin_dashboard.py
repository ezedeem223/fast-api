from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
from ..analytics import get_user_activity, get_problematic_users, get_ban_statistics
from datetime import date, timedelta
from sqlalchemy import func

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


async def get_current_admin(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


@router.get("/stats")
def get_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    try:
        post_count = db.query(models.Post).count()
        user_count = db.query(models.User).count()
        report_count = db.query(models.Report).count()
        community_count = db.query(models.Community).count()

        return {
            "total_posts": post_count,
            "total_users": user_count,
            "total_reports": report_count,
            "total_communities": community_count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching statistics.",
        )


@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    skip: int = 0,
    limit: int = 100,
):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


@router.put("/users/{user_id}/role", response_model=schemas.UserOut)
async def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_moderator = role_update.is_moderator
    user.is_admin = role_update.is_admin

    db.commit()
    db.refresh(user)
    return user


@router.get("/reports/overview")
async def get_reports_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    total_reports = db.query(models.Report).count()
    pending_reports = (
        db.query(models.Report).filter(models.Report.status == "pending").count()
    )
    resolved_reports = (
        db.query(models.Report).filter(models.Report.status == "resolved").count()
    )

    return {
        "total_reports": total_reports,
        "pending_reports": pending_reports,
        "resolved_reports": resolved_reports,
    }


@router.get("/communities/overview")
async def get_communities_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    total_communities = db.query(models.Community).count()
    active_communities = (
        db.query(models.Community).filter(models.Community.is_active == True).count()
    )

    return {
        "total_communities": total_communities,
        "active_communities": active_communities,
    }


@router.get("/user-activity/{user_id}")
def user_activity(
    user_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    return get_user_activity(db, user_id, days)


@router.get("/problematic-users", response_model=List[schemas.UserOut])
def problematic_users(
    threshold: int = 5,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    users = get_problematic_users(db, threshold)
    return [schemas.UserOut.from_orm(user) for user in users]


@router.get("/ban-statistics")
def ban_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    return get_ban_statistics(db)


@router.get("/ban-overview", response_model=schemas.BanStatisticsOverview)
async def get_ban_statistics_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    today = date.today()
    last_30_days = today - timedelta(days=30)

    stats = (
        db.query(models.BanStatistics)
        .filter(models.BanStatistics.date >= last_30_days)
        .all()
    )

    total_bans = sum(stat.total_bans for stat in stats)
    ip_bans = sum(stat.ip_bans for stat in stats)
    word_bans = sum(stat.word_bans for stat in stats)
    user_bans = sum(stat.user_bans for stat in stats)
    avg_effectiveness = (
        sum(stat.effectiveness_score for stat in stats) / len(stats) if stats else 0
    )

    return {
        "total_bans": total_bans,
        "ip_bans": ip_bans,
        "word_bans": word_bans,
        "user_bans": user_bans,
        "average_effectiveness": avg_effectiveness,
    }


@router.get("/common-ban-reasons", response_model=List[schemas.BanReasonOut])
async def get_common_ban_reasons(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    limit: int = 10,
):
    reasons = (
        db.query(models.BanReason)
        .order_by(models.BanReason.count.desc())
        .limit(limit)
        .all()
    )
    return reasons


@router.get("/ban-effectiveness-trend", response_model=List[schemas.EffectivenessTrend])
async def get_ban_effectiveness_trend(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = 30,
):
    today = date.today()
    start_date = today - timedelta(days=days)

    trend = (
        db.query(models.BanStatistics.date, models.BanStatistics.effectiveness_score)
        .filter(models.BanStatistics.date >= start_date)
        .order_by(models.BanStatistics.date)
        .all()
    )

    return [{"date": t.date, "effectiveness": t.effectiveness_score} for t in trend]


@router.get("/ban-type-distribution", response_model=schemas.BanTypeDistribution)
async def get_ban_type_distribution(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = 30,
):
    today = date.today()
    start_date = today - timedelta(days=days)

    distribution = (
        db.query(
            func.sum(models.BanStatistics.ip_bans).label("ip_bans"),
            func.sum(models.BanStatistics.word_bans).label("word_bans"),
            func.sum(models.BanStatistics.user_bans).label("user_bans"),
        )
        .filter(models.BanStatistics.date >= start_date)
        .first()
    )

    return {
        "ip_bans": distribution.ip_bans or 0,
        "word_bans": distribution.word_bans or 0,
        "user_bans": distribution.user_bans or 0,
    }
