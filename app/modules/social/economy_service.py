"""Helpers for the social domain."""
import math
from collections import defaultdict
from typing import Dict, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.posts.models import Post, Reaction
from app.modules.users.models import Badge, User, UserBadge

try:
    from app.modules.social import economy_accel
except Exception:
    economy_accel = None


class SocialEconomyService:
    """Service layer for SocialEconomyService."""
    def __init__(self, db: Session):
        self.db = db

    def calculate_quality_score(self, content: str) -> float:
        """Heuristic quality score based on length, formatting, and lexical diversity."""
        if economy_accel and economy_accel.AVAILABLE:
            return economy_accel.quality_score(content)
        score = 0.0
        length = len(content)

        if 50 <= length <= 2000:
            score += 40
        elif length > 2000:
            score += 20

        if "\n" in content:
            score += 10

        words = content.split()
        unique_words = set(words)
        if len(words) > 0:
            diversity_ratio = len(unique_words) / len(words)
            if diversity_ratio > 0.6:
                score += 30
            elif diversity_ratio > 0.4:
                score += 15

        score += 20

        return min(100.0, score)

    def calculate_engagement_score(self, post: Post) -> float:
        """Log-scaled engagement score combining reactions and comments."""
        likes_count = (
            self.db.query(Reaction).filter(Reaction.post_id == post.id).count()
        )
        comments_count = len(post.comments)
        return self._engagement_from_counts(likes_count, comments_count)

    def calculate_originality_score(self, post: Post) -> float:
        """Simple originality heuristic: penalize reposts heavily."""
        if post.is_repost:
            return 10.0

        return 90.0

    def update_post_score(self, post_id: int):
        """Aggregate quality/engagement/originality into total score and update user credits."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return

        q_score = self.calculate_quality_score(post.content)
        e_score = self.calculate_engagement_score(post)
        o_score = self.calculate_originality_score(post)

        total_score = (q_score * 0.5) + (e_score * 0.4) + (o_score * 0.1)

        post.quality_score = q_score
        post.originality_score = o_score
        post.score = total_score

        user = self.db.query(User).filter(User.id == post.owner_id).first()
        if user:
            credit_earned = total_score * 0.05
            user.social_credits += credit_earned

        self.db.commit()
        return total_score

    def bulk_update_post_scores(self, post_ids: Iterable[int]) -> Dict[int, float]:
        """
        Optimized batch scorer for multiple posts to reduce DB round-trips.

        Returns a mapping of post_id -> total_score.
        """
        ids = list(post_ids)
        if not ids:
            return {}

        # Preload posts in one query
        posts = self.db.query(Post).filter(Post.id.in_(ids)).all()
        if not posts:
            return {}

        # Aggregate reactions/comments counts in bulk
        reactions_counts: Dict[int, int] = defaultdict(int)
        for post_id, count in (
            self.db.query(Reaction.post_id, func.count(Reaction.id))
            .filter(Reaction.post_id.in_(ids))
            .group_by(Reaction.post_id)
            .all()
        ):
            reactions_counts[post_id] = count

        comments_counts: Dict[int, int] = defaultdict(int)
        for post_id, count in (
            self.db.query(Post.id, func.count(func.nullif(Post.id, None)))
            .join(Post.comments)
            .filter(Post.id.in_(ids))
            .group_by(Post.id)
            .all()
        ):
            comments_counts[post_id] = count

        scores: Dict[int, float] = {}
        for post in posts:
            likes = reactions_counts.get(post.id, 0)
            comments = comments_counts.get(post.id, 0)
            q_score = self.calculate_quality_score(post.content)
            e_score = self._engagement_from_counts(likes, comments)
            o_score = self.calculate_originality_score(post)
            total = (q_score * 0.5) + (e_score * 0.4) + (o_score * 0.1)
            post.quality_score = q_score
            post.originality_score = o_score
            post.score = total
            scores[post.id] = total
            # Credit user without extra query by using relationship
            if post.owner:
                post.owner.social_credits = (
                    post.owner.social_credits or 0
                ) + total * 0.05

        self.db.commit()
        return scores

    def _engagement_from_counts(self, likes_count: int, comments_count: int) -> float:
        if economy_accel and economy_accel.AVAILABLE:
            return economy_accel.engagement_score(likes_count, comments_count)
        raw_score = (likes_count * 1) + (comments_count * 2)
        if raw_score == 0:
            return 0.0
        normalized_score = math.log(raw_score + 1) * 20
        return min(100.0, normalized_score)

    # === [ADDITION START] ===
    def check_and_award_badges(self, user_id: int):
        """
        Check if the user qualifies for any new badges based on their stats.
        This should be called after a post is created or a score is updated.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return

        # Get all badges the user doesn't have yet
        existing_badge_ids = [
            b.badge_id
            for b in self.db.query(UserBadge).filter(UserBadge.user_id == user_id).all()
        ]
        potential_badges = (
            self.db.query(Badge).filter(~Badge.id.in_(existing_badge_ids)).all()
        )

        for badge in potential_badges:
            # Check thresholds (Dynamic Logic)
            posts_ok = user.post_count >= badge.required_posts
            score_ok = user.social_credits >= badge.required_score

            if posts_ok and score_ok:
                # Award the badge!
                new_badge = UserBadge(user_id=user.id, badge_id=badge.id)
                self.db.add(new_badge)
                # Notification logic can be added here

        self.db.commit()

    # === [ADDITION END] ===
