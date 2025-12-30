"""Statistics router for system/community analytics and user activity aggregates.

Primarily for admin/moderator insights; derives metrics via utility helpers and DB queries.
"""

from datetime import date, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.utils.analytics import get_user_vote_analytics
from fastapi import APIRouter, Depends, Query

# Import project modules
from .. import models, oauth2, schemas

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


@router.get("/top-posts", response_model=List[schemas.TopPostStat])
async def get_top_posts(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    Return the most engaging posts ranked by votes and comment counts.
    """
    posts = (
        db.query(
            models.Post.id,
            models.Post.title,
            func.coalesce(models.Post.votes, 0).label("votes"),
            func.coalesce(models.Post.comment_count, 0).label("comment_count"),
        )
        .order_by(
            func.coalesce(models.Post.votes, 0).desc(),
            func.coalesce(models.Post.comment_count, 0).desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        schemas.TopPostStat(
            id=post.id,
            title=post.title,
            votes=post.votes or 0,
            comment_count=post.comment_count or 0,
        )
        for post in posts
    ]


@router.get("/top-users", response_model=List[schemas.TopUserStat])
async def get_top_users(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    Return the most active community members based on followers and publishing activity.
    """
    followers_subq = (
        db.query(
            models.Follow.followed_id.label("user_id"),
            func.count(models.Follow.follower_id).label("followers"),
        )
        .group_by(models.Follow.followed_id)
        .subquery()
    )

    users = (
        db.query(
            models.User.id,
            models.User.email,
            models.User.username,
            func.coalesce(models.User.post_count, 0).label("post_count"),
            func.coalesce(models.User.comment_count, 0).label("comment_count"),
            func.coalesce(followers_subq.c.followers, 0).label("followers"),
        )
        .outerjoin(followers_subq, followers_subq.c.user_id == models.User.id)
        .order_by(
            func.coalesce(followers_subq.c.followers, 0).desc(),
            func.coalesce(models.User.post_count, 0).desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        schemas.TopUserStat(
            id=user.id,
            email=user.email,
            username=user.username,
            followers=user.followers or 0,
            post_count=user.post_count or 0,
            comment_count=user.comment_count or 0,
        )
        for user in users
    ]
