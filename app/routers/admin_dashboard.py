from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional
from ..analytics import get_user_activity, get_problematic_users, get_ban_statistics
from datetime import date, timedelta
from ..utils import cache  # افتراض أننا أضفنا وظيفة للتخزين المؤقت

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


async def get_current_admin(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """التحقق من أن المستخدم الحالي هو مسؤول."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


@router.get("/stats")
@cache(expire=300)  # تخزين مؤقت لمدة 5 دقائق
async def get_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على الإحصائيات العامة للنظام."""
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
            detail=f"An error occurred while fetching statistics: {str(e)}",
        )


@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    sort_by: str = Query("id", description="Field to sort by"),
    order: str = Query("asc", description="Sort order (asc or desc)"),
):
    """الحصول على قائمة المستخدمين مع إمكانية الترتيب والتصفية."""
    try:
        query = db.query(models.User)

        # تطبيق الترتيب
        if hasattr(models.User, sort_by):
            order_column = getattr(models.User, sort_by)
            if order == "desc":
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))

        users = query.offset(skip).limit(limit).all()
        return users
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching users: {str(e)}",
        )


@router.put("/users/{user_id}/role", response_model=schemas.UserOut)
async def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """تحديث دور المستخدم."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_moderator = role_update.is_moderator
    user.is_admin = role_update.is_admin

    db.commit()
    db.refresh(user)
    return user


@router.get("/reports/overview")
@cache(expire=300)
async def get_reports_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على التقارير."""
    try:
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching report overview: {str(e)}",
        )


@router.get("/communities/overview")
@cache(expire=300)
async def get_communities_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على المجتمعات."""
    try:
        total_communities = db.query(models.Community).count()
        active_communities = (
            db.query(models.Community)
            .filter(models.Community.is_active == True)
            .count()
        )

        return {
            "total_communities": total_communities,
            "active_communities": active_communities,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching communities overview: {str(e)}",
        )


@router.get("/user-activity/{user_id}")
async def user_activity(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نشاط المستخدم خلال فترة محددة."""
    try:
        return get_user_activity(db, user_id, days)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching user activity: {str(e)}",
        )


@router.get("/problematic-users", response_model=List[schemas.UserOut])
async def problematic_users(
    threshold: int = Query(5, ge=1),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على قائمة المستخدمين المشكلين."""
    try:
        users = get_problematic_users(db, threshold)
        return [schemas.UserOut.from_orm(user) for user in users]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching problematic users: {str(e)}",
        )


@router.get("/ban-statistics")
@cache(expire=300)
async def ban_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على إحصائيات الحظر."""
    try:
        return get_ban_statistics(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban statistics: {str(e)}",
        )


@router.get("/ban-overview", response_model=schemas.BanStatisticsOverview)
@cache(expire=300)
async def get_ban_statistics_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على إحصائيات الحظر."""
    try:
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban statistics overview: {str(e)}",
        )


@router.get("/common-ban-reasons", response_model=List[schemas.BanReasonOut])
async def get_common_ban_reasons(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("count", description="Field to sort by (count or reason)"),
    order: str = Query("desc", description="Sort order (asc or desc)"),
):
    """الحصول على الأسباب الشائعة للحظر."""
    try:
        query = db.query(models.BanReason)

        if sort_by == "count":
            query = query.order_by(
                desc(models.BanReason.count)
                if order == "desc"
                else asc(models.BanReason.count)
            )
        elif sort_by == "reason":
            query = query.order_by(
                desc(models.BanReason.reason)
                if order == "desc"
                else asc(models.BanReason.reason)
            )

        reasons = query.limit(limit).all()
        return reasons
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching common ban reasons: {str(e)}",
        )


@router.get("/ban-effectiveness-trend", response_model=List[schemas.EffectivenessTrend])
@cache(expire=300)
async def get_ban_effectiveness_trend(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على اتجاه فعالية الحظر."""
    try:
        today = date.today()
        start_date = today - timedelta(days=days)

        trend = (
            db.query(
                models.BanStatistics.date, models.BanStatistics.effectiveness_score
            )
            .filter(models.BanStatistics.date >= start_date)
            .order_by(models.BanStatistics.date)
            .all()
        )

        return [{"date": t.date, "effectiveness": t.effectiveness_score} for t in trend]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban effectiveness trend: {str(e)}",
        )


@router.get("/ban-type-distribution", response_model=schemas.BanTypeDistribution)
@cache(expire=300)
async def get_ban_type_distribution(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على توزيع أنواع الحظر."""
    try:
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban type distribution: {str(e)}",
        )
