"""Analytics and scoring utilities.

Heuristics:
- Post scoring favors recency via power decay; retains higher prior scores to avoid regressions across recalculations.
- Call quality buffer keeps a small rolling window and cleans idle entries; thresholds are coarse by design.
- Sentiment/relevance is lightweight and only directionally useful; not intended for hard moderation gates.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import date, datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.modules.posts.models import (
    Post,
    PostCategory,
    PostVoteStatistics,
    Reaction,
    ReactionType,
)

from .content import sentiment_pipeline


def update_ban_statistics(db: Session, target: str, reason: str, score: float) -> None:
    """Increment moderation/ban statistics; tolerate missing rows by creating for today."""
    today = datetime.now(timezone.utc).date()
    stats = (
        db.query(models.BanStatistics)
        .filter(models.BanStatistics.date == today)
        .first()
    )
    if not stats:
        stats = models.BanStatistics(
            date=today, total_bans=0, ip_bans=0, word_bans=0, user_bans=0
        )
        db.add(stats)
        db.flush()

    stats.total_bans = (stats.total_bans or 0) + 1
    if target == "ip":
        stats.ip_bans = (stats.ip_bans or 0) + 1
    elif target == "word":
        stats.word_bans = (stats.word_bans or 0) + 1
    else:
        stats.user_bans = (stats.user_bans or 0) + 1

    stats.effectiveness_score = score
    stats.most_common_reason = reason
    db.commit()


QUALITY_WINDOW_SIZE = 10
MIN_QUALITY_THRESHOLD = 50


def create_default_categories(db: Session):
    """Create default post categories and subcategories if missing."""
    # Seed core categories and add scoped subcategories only when the parent is new.
    default_categories = [
        {"name": "Work", "description": "Posts related to job opportunities"},
        {
            "name": "Migration",
            "description": "Information and experiences about migration",
        },
        {"name": "Asylum", "description": "Posts regarding asylum procedures"},
    ]
    for category in default_categories:
        db_category = (
            db.query(PostCategory).filter(PostCategory.name == category["name"]).first()
        )
        if not db_category:
            new_category = PostCategory(**category)
            db.add(new_category)
            db.commit()
            db.refresh(new_category)
            # Derive subcategories from the parent name for consistent taxonomy.
            if category["name"] == "Work":
                sub_categories = ["Work in Canada", "Work in USA", "Work in Europe"]
            elif category["name"] == "Migration":
                sub_categories = [
                    "Migration to Canada",
                    "Migration to USA",
                    "Migration to Australia",
                ]
            elif category["name"] == "Asylum":
                sub_categories = [
                    "Asylum in Europe",
                    "Asylum in Canada",
                    "Asylum in USA",
                ]
            else:
                sub_categories = []
            for sub_cat in sub_categories:
                exists = (
                    db.query(PostCategory).filter(PostCategory.name == sub_cat).first()
                )
                if not exists:
                    db.add(PostCategory(name=sub_cat, parent_id=new_category.id))
    db.commit()


def update_user_statistics(db: Session, user_id: int, action: str):
    """Update user statistics based on action."""
    today = date.today()
    stats = (
        db.query(models.UserStatistics)
        .filter(
            models.UserStatistics.user_id == user_id,
            models.UserStatistics.date == today,
        )
        .first()
    )
    if not stats:
        stats = models.UserStatistics(user_id=user_id, date=today)
        db.add(stats)
    if action == "post":
        stats.post_count += 1
    elif action == "comment":
        stats.comment_count += 1
    elif action == "like":
        stats.like_count += 1
    elif action == "view":
        stats.view_count += 1
    db.commit()


def analyze_user_behavior(user_history, content: str) -> float:
    """Analyze user behavior based on search history and sentiment."""
    user_interests = set(item.lower() for item in user_history)
    result = sentiment_pipeline(content[:512])[0]
    sentiment = result["label"]
    score = result["score"]
    relevance_score = sum(
        1 for word in content.lower().split() if word in user_interests
    )
    relevance_score += score if sentiment == "POSITIVE" else 0
    return relevance_score


def calculate_post_score(
    upvotes: int, downvotes: int, comment_count: int, created_at: datetime
) -> float:
    """Calculate score considering vote delta, comments, and age with decay to favor recency."""
    vote_difference = upvotes - downvotes
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0
    score = (vote_difference + comment_count) / (age_hours + 2) ** 1.8
    return score


def update_post_score(db: Session, post: Post):
    """Update a post's score using reactions, comment count, and age."""
    reactions = db.query(Reaction).filter(Reaction.post_id == post.id).all()

    reaction_weights = {
        "like": 1,
        "love": 2,
        "haha": 1.5,
        "wow": 1.5,
        "sad": 1,
        "angry": 1,
    }

    score = sum(
        reaction_weights.get(reaction.reaction_type, 1) for reaction in reactions
    )
    score += post.comment_count * 0.5

    created_at = post.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0
    score = score / (age_hours + 2) ** 1.8

    # Avoid regressions when another scoring system already set a higher score
    post.score = max(post.score or 0, score)
    db.commit()


def update_post_vote_statistics(db: Session, post_id: int):
    """Update aggregated reaction statistics for a post."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return

    stats = post.vote_statistics or PostVoteStatistics(post_id=post_id)

    reactions = db.query(Reaction).filter(Reaction.post_id == post_id).all()
    positive_types = {"like", "love", "haha", "wow"}
    negative_types = {"sad", "angry"}

    stats.total_votes = len(reactions)
    stats.upvotes = sum(
        1 for reaction in reactions if reaction.reaction_type in positive_types
    )
    stats.downvotes = sum(
        1 for reaction in reactions if reaction.reaction_type in negative_types
    )

    for reaction_type in ReactionType:
        count = sum(
            1 for reaction in reactions if reaction.reaction_type == reaction_type.value
        )
        setattr(stats, f"{reaction_type.value}_count", count)

    post.vote_statistics = stats
    db.add(stats)
    db.commit()


def get_user_vote_analytics(db: Session, user_id: int) -> schemas.UserVoteAnalytics:
    """Generate vote analytics for a user's posts."""
    user_posts = db.query(Post).filter(Post.owner_id == user_id).all()
    total_posts = len(user_posts)
    total_votes = sum(
        post.vote_statistics.total_votes for post in user_posts if post.vote_statistics
    )
    if total_posts == 0:
        return schemas.UserVoteAnalytics(
            total_posts=0,
            total_votes_received=0,
            average_votes_per_post=0,
            most_upvoted_post=None,
            most_downvoted_post=None,
            most_reacted_post=None,
        )
    average_votes = total_votes / total_posts
    most_upvoted = max(
        user_posts, key=lambda p: p.vote_statistics.upvotes if p.vote_statistics else 0
    )
    most_downvoted = max(
        user_posts,
        key=lambda p: p.vote_statistics.downvotes if p.vote_statistics else 0,
    )
    most_reacted = max(
        user_posts,
        key=lambda p: p.vote_statistics.total_votes if p.vote_statistics else 0,
    )
    return schemas.UserVoteAnalytics(
        total_posts=total_posts,
        total_votes_received=total_votes,
        average_votes_per_post=average_votes,
        most_upvoted_post=create_post_vote_analytics(most_upvoted),
        most_downvoted_post=create_post_vote_analytics(most_downvoted),
        most_reacted_post=create_post_vote_analytics(most_reacted),
    )


def create_post_vote_analytics(
    post: Post,
) -> Optional[schemas.PostVoteAnalytics]:
    """Create analytics snapshot for a specific post."""
    stats = post.vote_statistics
    if not stats:
        return None
    total_votes = stats.total_votes or 1
    upvote_percentage = (stats.upvotes / total_votes) * 100
    downvote_percentage = (stats.downvotes / total_votes) * 100
    reaction_counts = {
        "like": stats.like_count,
        "love": stats.love_count,
        "haha": stats.haha_count,
        "wow": stats.wow_count,
        "sad": stats.sad_count,
        "angry": stats.angry_count,
    }
    most_common_reaction = max(reaction_counts, key=reaction_counts.get)
    return schemas.PostVoteAnalytics(
        post_id=post.id,
        title=post.title,
        statistics=schemas.PostVoteStatistics.model_validate(stats),
        upvote_percentage=upvote_percentage,
        downvote_percentage=downvote_percentage,
        most_common_reaction=most_common_reaction,
    )


class CallQualityBuffer:
    """Store call quality scores within a time window."""

    def __init__(self, window_size: int = QUALITY_WINDOW_SIZE):
        self.window_size = window_size
        self.quality_scores = deque(maxlen=window_size)
        self.last_update_time = time.time()

    def add_score(self, score: float) -> None:
        self.quality_scores.append(score)
        self.last_update_time = time.time()

    def get_average_score(self) -> float:
        if not self.quality_scores:
            return 100.0
        return sum(self.quality_scores) / len(self.quality_scores)


quality_buffers: Dict[str, CallQualityBuffer] = {}


def check_call_quality(data: dict, call_id: str) -> float:
    """Calculate call quality score from packet loss, latency, and jitter."""
    packet_loss = data.get("packet_loss", 0)
    latency = data.get("latency", 0)
    jitter = data.get("jitter", 0)
    quality_score = 100 - (packet_loss * 2 + latency / 10 + jitter)
    if call_id not in quality_buffers:
        quality_buffers[call_id] = CallQualityBuffer()
    quality_buffers[call_id].add_score(quality_score)
    return quality_buffers[call_id].get_average_score()


def should_adjust_video_quality(call_id: str) -> bool:
    """Determine if video quality should be adjusted based on average score."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        return average_quality < MIN_QUALITY_THRESHOLD
    return False


def get_recommended_video_quality(call_id: str) -> str:
    """Recommend video quality level based on average score."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        if average_quality < 30:
            return "low"
        if average_quality < 60:
            return "medium"
        return "high"
    return "high"


def clean_old_quality_buffers():
    """Remove call quality buffers older than 5 minutes."""
    current_time = time.time()
    for call_id in list(quality_buffers.keys()):
        if current_time - quality_buffers[call_id].last_update_time > 300:
            del quality_buffers[call_id]


__all__ = [
    "create_default_categories",
    "update_user_statistics",
    "analyze_user_behavior",
    "calculate_post_score",
    "update_post_score",
    "update_post_vote_statistics",
    "get_user_vote_analytics",
    "create_post_vote_analytics",
    "CallQualityBuffer",
    "quality_buffers",
    "check_call_quality",
    "should_adjust_video_quality",
    "get_recommended_video_quality",
    "clean_old_quality_buffers",
    "QUALITY_WINDOW_SIZE",
    "MIN_QUALITY_THRESHOLD",
]
