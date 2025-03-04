from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import date, timedelta

# Import project modules
from .. import models, schemas, oauth2
from ..database import get_db
from ..utils import get_user_vote_analytics

router = APIRouter(prefix="/statistics", tags=["Statistics"])

# ------------------------------------------------------------------
#                         Endpoints
# ------------------------------------------------------------------


@router.get("/vote-analytics", response_model=schemas.UserVoteAnalytics)
def get_vote_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve vote analytics for the current user.
    This endpoint calls a utility function to process user vote data.
    """
    return get_user_vote_analytics(db, current_user.id)


@router.get("/comments", response_model=schemas.CommentStatistics)
async def get_comment_statistics(db: Session = Depends(get_db)):
    """
    Retrieve statistics about comments.
    - total_comments: Total number of comments.
    - top_commenters: Top 5 users with the highest comment counts.
    - most_commented_posts: Top 5 posts with the highest comment counts.
    - average_sentiment: Average sentiment score of comments.
    """
    total_comments = db.query(func.count(models.Comment.id)).scalar()

    top_commenters = (
        db.query(
            models.User.id,
            models.User.username,
            func.count(models.Comment.id).label("comment_count"),
        )
        .join(models.Comment)
        .group_by(models.User.id)
        .order_by(func.count(models.Comment.id).desc())
        .limit(5)
        .all()
    )

    most_commented_posts = (
        db.query(
            models.Post.id,
            models.Post.title,
            func.count(models.Comment.id).label("comment_count"),
        )
        .join(models.Comment)
        .group_by(models.Post.id)
        .order_by(func.count(models.Comment.id).desc())
        .limit(5)
        .all()
    )

    avg_sentiment = db.query(func.avg(models.Comment.sentiment_score)).scalar()

    return {
        "total_comments": total_comments,
        "top_commenters": top_commenters,
        "most_commented_posts": most_commented_posts,
        "average_sentiment": avg_sentiment,
    }


@router.get("/ban-overview", response_model=schemas.BanStatisticsOverview)
async def get_ban_statistics_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    Provide an overview of ban statistics for the last 30 days.
    Aggregates total bans, IP bans, word bans, and user bans.
    Also calculates the average effectiveness score of bans.
    """
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
    current_user: models.User = Depends(oauth2.get_current_admin),
    limit: int = 10,
):
    """
    Retrieve a list of the most common ban reasons.
    The list is ordered by the count of each ban reason in descending order.
    """
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
    current_user: models.User = Depends(oauth2.get_current_admin),
    days: int = 30,
):
    """
    Retrieve the trend of ban effectiveness scores over a specified number of days.
    Returns a list of dates with their corresponding effectiveness scores.
    """
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
    current_user: models.User = Depends(oauth2.get_current_admin),
    days: int = 30,
):
    """
    Retrieve the distribution of different ban types (IP bans, word bans, user bans)
    over a specified number of days.
    """
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
