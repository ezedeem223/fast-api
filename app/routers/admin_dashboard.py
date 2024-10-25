"""
Admin Dashboard Router Module
يوفر نقاط النهاية الخاصة بلوحة تحكم المسؤول مع وظائف التحليلات والإحصائيات
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from typing import List, Optional
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta
from ..utils import cache

from .. import models, schemas, oauth2
from ..database import get_db
from ..analytics import (
    get_user_activity,
    get_problematic_users,
    get_ban_statistics,
    get_popular_searches,
    get_recent_searches,
    generate_search_trends_chart,
)

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])
templates = Jinja2Templates(directory="app/templates")


# لوحة التحكم الرئيسية
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: models.User = Depends(oauth2.get_current_admin),
    db: Session = Depends(get_db),
):
    """عرض لوحة التحكم الرئيسية للمسؤول"""
    search_trends_chart = generate_search_trends_chart()
    popular_searches = get_popular_searches(db, limit=10)
    recent_searches = get_recent_searches(db, limit=10)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "search_trends_chart": search_trends_chart,
            "popular_searches": popular_searches,
            "recent_searches": recent_searches,
        },
    )


# التحقق من صلاحيات المسؤول
async def get_current_admin(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """التحقق من صلاحيات المسؤول"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


# الإحصائيات العامة
@router.get("/stats")
@cache(expire=300)  # تخزين مؤقت لمدة 5 دقائق
async def get_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على الإحصائيات العامة للنظام"""
    try:
        stats = {
            "total_posts": db.query(models.Post).count(),
            "total_users": db.query(models.User).count(),
            "total_reports": db.query(models.Report).count(),
            "total_communities": db.query(models.Community).count(),
        }
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching statistics: {str(e)}",
        )


# إدارة المستخدمين
@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    sort_by: str = Query("id", description="Field to sort by"),
    order: str = Query("asc", description="Sort order (asc or desc)"),
):
    """الحصول على قائمة المستخدمين مع إمكانية الترتيب والتصفية"""
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


# تحديث دور المستخدم
@router.put("/users/{user_id}/role", response_model=schemas.UserOut)
async def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """تحديث دور المستخدم"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_moderator = role_update.is_moderator
    user.is_admin = role_update.is_admin

    db.commit()
    db.refresh(user)
    return user


# نظرة عامة على التقارير
@router.get("/reports/overview")
@cache(expire=300)
async def get_reports_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على التقارير"""
    try:
        stats = {
            "total_reports": db.query(models.Report).count(),
            "pending_reports": db.query(models.Report)
            .filter(models.Report.status == "pending")
            .count(),
            "resolved_reports": db.query(models.Report)
            .filter(models.Report.status == "resolved")
            .count(),
        }
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching report overview: {str(e)}",
        )


# نظرة عامة على المجتمعات
@router.get("/communities/overview")
@cache(expire=300)
async def get_communities_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على المجتمعات"""
    try:
        stats = {
            "total_communities": db.query(models.Community).count(),
            "active_communities": db.query(models.Community)
            .filter(models.Community.is_active == True)
            .count(),
        }
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching communities overview: {str(e)}",
        )


# نشاط المستخدم
@router.get("/user-activity/{user_id}")
async def user_activity(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نشاط المستخدم خلال فترة محددة"""
    try:
        return get_user_activity(db, user_id, days)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching user activity: {str(e)}",
        )


# المستخدمين المشكلين
@router.get("/problematic-users", response_model=List[schemas.UserOut])
async def problematic_users(
    threshold: int = Query(5, ge=1),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على قائمة المستخدمين المشكلين"""
    try:
        users = get_problematic_users(db, threshold)
        return [schemas.UserOut.from_orm(user) for user in users]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching problematic users: {str(e)}",
        )


# إحصائيات الحظر
@router.get("/ban-statistics")
@cache(expire=300)
async def ban_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على إحصائيات الحظر"""
    try:
        return get_ban_statistics(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban statistics: {str(e)}",
        )


# نظرة عامة على إحصائيات الحظر
@router.get("/ban-overview", response_model=schemas.BanStatisticsOverview)
@cache(expire=300)
async def get_ban_statistics_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """الحصول على نظرة عامة على إحصائيات الحظر"""
    try:
        thirty_days_ago = date.today() - timedelta(days=30)
        stats = (
            db.query(models.BanStatistics)
            .filter(models.BanStatistics.date >= thirty_days_ago)
            .all()
        )

        overview = {
            "total_bans": sum(stat.total_bans for stat in stats),
            "ip_bans": sum(stat.ip_bans for stat in stats),
            "word_bans": sum(stat.word_bans for stat in stats),
            "user_bans": sum(stat.user_bans for stat in stats),
            "average_effectiveness": (
                sum(stat.effectiveness_score for stat in stats) / len(stats)
                if stats
                else 0
            ),
        }
        return overview
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban statistics overview: {str(e)}",
        )


# أسباب الحظر الشائعة
@router.get("/common-ban-reasons", response_model=List[schemas.BanReasonOut])
async def get_common_ban_reasons(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("count", description="Field to sort by (count or reason)"),
    order: str = Query("desc", description="Sort order (asc or desc)"),
):
    """الحصول على أسباب الحظر الشائعة"""
    try:
        query = db.query(models.BanReason)

        # تطبيق الترتيب
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


# اتجاه فعالية الحظر
@router.get("/ban-effectiveness-trend", response_model=List[schemas.EffectivenessTrend])
@cache(expire=300)
async def get_ban_effectiveness_trend(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على اتجاه فعالية الحظر"""
    try:
        start_date = date.today() - timedelta(days=days)
        trend = (
            db.query(
                models.BanStatistics.date,
                models.BanStatistics.effectiveness_score,
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


# توزيع أنواع الحظر
@router.get("/ban-type-distribution", response_model=schemas.BanTypeDistribution)
@cache(expire=300)
async def get_ban_type_distribution(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على توزيع أنواع الحظر"""
    try:
        start_date = date.today() - timedelta(days=days)
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
