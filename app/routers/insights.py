"""API endpoints for advanced growth and retention insights."""

from __future__ import annotations

from datetime import date
from typing import Iterable, List

from fastapi import APIRouter

from .. import analytics
from ..insights import CohortPerformance, build_insight_summary, calculate_momentum
from ..schemas import CohortInput, InsightsRequest

router = APIRouter(prefix="/insights", tags=["insights"])


def _convert_cohorts(payload: Iterable[CohortInput]) -> List[CohortPerformance]:
    """Convert request payload cohorts into :class:`CohortPerformance` objects."""

    cohorts: List[CohortPerformance] = []
    for cohort in payload:
        start = cohort.start_date if isinstance(cohort.start_date, date) else date.fromisoformat(cohort.start_date)
        cohorts.append(CohortPerformance(cohort_start=start, size=cohort.size, returning=cohort.returning))
    return cohorts


@router.post("/summary")
def summarize_product_health(request: InsightsRequest):
    """Return a holistic summary that blends retention, growth, and sentiment."""

    cohorts = _convert_cohorts(request.cohorts)

    sentiment_score = request.sentiment_score
    feedback_details: List[str] = []
    if request.feedback_samples:
        sentiments = [analytics.analyze_content(text)["sentiment"]["score"] for text in request.feedback_samples]
        if sentiments:
            sentiment_score = sum(sentiments) / len(sentiments)
        feedback_details = request.feedback_samples

    churned = request.churned_users or [0] * len(request.new_signups)

    summary = build_insight_summary(
        cohorts=cohorts,
        daily_active_users=request.daily_active_users,
        new_signups=request.new_signups,
        churned_users=churned,
        feature_usage=request.feature_usage,
        sentiment_score=sentiment_score,
    )

    summary["feedback"] = {
        "sample_count": len(feedback_details),
        "notes": feedback_details[:10],
        "average_sentiment": round(sentiment_score, 4),
    }
    return summary


@router.post("/momentum")
def calculate_momentum_breakdown(request: InsightsRequest):
    """Expose the raw momentum breakdown for dashboard drill-downs."""

    churned = request.churned_users or [0] * len(request.new_signups)

    return calculate_momentum(
        daily_active_users=request.daily_active_users,
        new_signups=request.new_signups,
        churned_users=churned,
    )
