"""
Admin Dashboard Router Module
This module provides endpoints for the admin dashboard,
including analytics and statistics functions.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from datetime import date, timedelta
from typing import List

# Local imports
from .. import models, schemas, oauth2
from app.modules.community import Community
from app.core.database import get_db
from ..analytics import (
    get_user_activity,
    get_problematic_users,
    get_ban_statistics,
    get_popular_searches,
    get_recent_searches,
    generate_search_trends_chart,
)

# استبدال استيراد cache من utils بالاستيراد من cachetools
from cachetools import cached, TTLCache

# =====================================================
# =============== Global Variables ====================
# =====================================================
router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])
templates = Jinja2Templates(directory="app/templates")

# تعريف كائن التخزين المؤقت للإدارة بمهلة انتهاء 5 دقائق (300 ثانية)
admin_cache = TTLCache(maxsize=100, ttl=300)

# =====================================================
# =================== Endpoints =======================
# =====================================================


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: models.User = Depends(oauth2.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Main admin dashboard view.
    Retrieves search trends, popular searches, and recent searches
    to render the admin dashboard template.
    """
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


# -----------------------------------------------------
# Helper function for Admin Authentication
# -----------------------------------------------------
async def get_current_admin(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Verify that the current user has admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


# -----------------------------------------------------
# General Statistics Endpoint
# -----------------------------------------------------
@router.get("/stats")
@cached(admin_cache)  # Cache for 5 minutes
async def get_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Get overall system statistics.
    Returns counts for posts, users, reports, and communities.
    """
    try:
        stats = {
            "total_posts": db.query(models.Post).count(),
            "total_users": db.query(models.User).count(),
            "total_reports": db.query(models.Report).count(),
            "total_communities": db.query(Community).count(),
        }
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching statistics: {str(e)}",
        )


# -----------------------------------------------------
# Users Management Endpoints
# -----------------------------------------------------
@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    sort_by: str = Query("id", description="Field to sort by"),
    order: str = Query("asc", description="Sort order (asc or desc)"),
):
    """
    Retrieve a list of users with optional sorting and filtering.
    """
    try:
        query = db.query(models.User)
        # Apply sorting if the attribute exists in the User model.
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
    """
    Update a user's role (e.g. moderator, admin).
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_moderator = role_update.is_moderator
    user.is_admin = role_update.is_admin
    db.commit()
    db.refresh(user)
    return user


# -----------------------------------------------------
# Reports Overview Endpoint
# -----------------------------------------------------
@router.get("/reports/overview")
@cached(admin_cache)
async def get_reports_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Get an overview of reports.
    Returns total reports, pending reports, and resolved reports counts.
    """
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


# -----------------------------------------------------
# Communities Overview Endpoint
# -----------------------------------------------------
@router.get("/communities/overview")
@cached(admin_cache)
async def get_communities_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Get an overview of communities.
    Returns total communities and active communities counts.
    """
    try:
        stats = {
            "total_communities": db.query(Community).count(),
            "active_communities": db.query(Community)
            .filter(Community.is_active)
            .count(),
        }
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching communities overview: {str(e)}",
        )


# -----------------------------------------------------
# User Activity Endpoint
# -----------------------------------------------------
@router.get("/user-activity/{user_id}")
async def user_activity(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Retrieve user activity for a specified number of days.
    """
    try:
        return get_user_activity(db, user_id, days)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching user activity: {str(e)}",
        )


# -----------------------------------------------------
# Problematic Users Endpoint
# -----------------------------------------------------
@router.get("/problematic-users", response_model=List[schemas.UserOut])
async def problematic_users(
    threshold: int = Query(5, ge=1),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Retrieve a list of problematic users based on a threshold.
    """
    try:
        users = get_problematic_users(db, threshold)
        return [schemas.UserOut.model_validate(user) for user in users]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching problematic users: {str(e)}",
        )


# -----------------------------------------------------
# Ban Statistics Endpoints
# -----------------------------------------------------
@router.get("/ban-statistics")
@cached(admin_cache)
async def ban_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Retrieve ban statistics.
    """
    try:
        return get_ban_statistics(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching ban statistics: {str(e)}",
        )


@router.get("/ban-overview", response_model=schemas.BanStatisticsOverview)
@cached(admin_cache)
async def get_ban_statistics_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    Retrieve an overview of ban statistics for the last 30 days.
    """
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
                (sum(stat.effectiveness_score for stat in stats) / len(stats))
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


@router.get("/common-ban-reasons", response_model=List[schemas.BanReasonOut])
async def get_common_ban_reasons(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("count", description="Field to sort by (count or reason)"),
    order: str = Query("desc", description="Sort order (asc or desc)"),
):
    """
    Retrieve common ban reasons with sorting options.
    """
    try:
        query = db.query(models.BanReason)
        if sort_by == "count":
            query = (
                query.order_by(desc(models.BanReason.count))
                if order == "desc"
                else query.order_by(asc(models.BanReason.count))
            )
        elif sort_by == "reason":
            query = (
                query.order_by(desc(models.BanReason.reason))
                if order == "desc"
                else query.order_by(asc(models.BanReason.reason))
            )
        reasons = query.limit(limit).all()
        return reasons
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching common ban reasons: {str(e)}",
        )


@router.get("/ban-effectiveness-trend", response_model=List[schemas.EffectivenessTrend])
@cached(admin_cache)
async def get_ban_effectiveness_trend(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """
    Retrieve the trend of ban effectiveness over a specified number of days.
    """
    try:
        start_date = date.today() - timedelta(days=days)
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
@cached(admin_cache)
async def get_ban_type_distribution(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
):
    """
    Retrieve the distribution of different ban types over a specified period.
    """
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
