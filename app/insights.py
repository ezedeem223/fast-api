"""Advanced growth and retention insight helpers.

This module provides higher-level analytics that complement the lighter
utilities in :mod:`app.analytics`.  The functions defined here intentionally
avoid heavy numerical dependencies so they can run inside automated tests while
still delivering distinctive metrics that product teams can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Dict, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CohortPerformance:
    """Represent retention information for a single cohort.

    The structure keeps the original cohort size together with the number of
    returning users.  Helper properties compute retention metrics that are used
    throughout the summary helpers and exposed via the Insights API.
    """

    cohort_start: date
    size: int
    returning: int

    @property
    def retention_rate(self) -> float:
        """Return the retention percentage for the cohort."""

        if self.size <= 0:
            return 0.0
        return round(self.returning / self.size, 4)

    def to_dict(self) -> Dict[str, object]:
        """Serialise the cohort for API responses."""

        return {
            "cohort_start": self.cohort_start.isoformat(),
            "size": self.size,
            "returning": self.returning,
            "retention_rate": self.retention_rate,
        }


def calculate_retention(cohorts: Sequence[CohortPerformance]) -> Dict[str, object]:
    """Return retention information for each cohort and the overall average."""

    rates = [cohort.retention_rate for cohort in cohorts]
    average = round(mean(rates), 4) if rates else 0.0
    return {
        "average_retention": average,
        "cohorts": [cohort.to_dict() for cohort in cohorts],
    }


def calculate_momentum(
    daily_active_users: Sequence[int],
    new_signups: Sequence[int],
    churned_users: Sequence[int],
) -> Dict[str, float]:
    """Calculate a lightweight momentum score for the product.

    The implementation derives three interpretable sub-metrics:

    * growth rate compares new sign-ups against churn.
    * activation ratio checks how many sign-ups became active users.
    * volatility penalty discourages wild swings in the active user numbers.

    The overall momentum is a harmonic blend of the three components.
    """

    if not daily_active_users or not new_signups:
        return {"growth_rate": 0.0, "activation_ratio": 0.0, "volatility_penalty": 0.0, "momentum": 0.0}

    total_new = sum(new_signups)
    total_churn = max(sum(churned_users), 1)
    growth_rate = round(total_new / total_churn, 4)

    avg_active = mean(daily_active_users)
    activation_ratio = round(avg_active / max(total_new, 1), 4)

    if len(daily_active_users) > 1:
        diffs = [abs(daily_active_users[i] - daily_active_users[i - 1]) for i in range(1, len(daily_active_users))]
        volatility_penalty = round(1 / (1 + mean(diffs)), 4)
    else:
        volatility_penalty = 1.0

    momentum = round((growth_rate * activation_ratio * volatility_penalty) ** (1 / 3), 4)
    return {
        "growth_rate": growth_rate,
        "activation_ratio": activation_ratio,
        "volatility_penalty": volatility_penalty,
        "momentum": momentum,
    }


def generate_product_health_index(
    feature_usage: Mapping[str, int],
    sentiment_score: float,
    momentum_score: float,
) -> Dict[str, object]:
    """Combine qualitative and quantitative signals into a single index."""

    if not feature_usage:
        return {
            "health_score": round(min(max((sentiment_score + momentum_score) / 2, 0.0), 1.0), 4),
            "feature_focus": [],
        }

    total_usage = sum(max(value, 0) for value in feature_usage.values()) or 1
    ordered = sorted(feature_usage.items(), key=lambda item: item[1], reverse=True)
    focus = [
        {"feature": feature, "adoption": round(value / total_usage, 4)}
        for feature, value in ordered
    ][:5]

    health_score = round(min(max((sentiment_score * 0.4) + (momentum_score * 0.6), 0.0), 1.0), 4)
    return {"health_score": health_score, "feature_focus": focus}


def build_insight_summary(
    *,
    cohorts: Iterable[CohortPerformance],
    daily_active_users: Sequence[int],
    new_signups: Sequence[int],
    churned_users: Sequence[int],
    feature_usage: Mapping[str, int],
    sentiment_score: float,
) -> Dict[str, object]:
    """Create a complete summary suitable for dashboards and reports."""

    cohorts_list = list(cohorts)
    retention = calculate_retention(cohorts_list)
    momentum = calculate_momentum(daily_active_users, new_signups, churned_users)
    health = generate_product_health_index(feature_usage, sentiment_score, momentum["momentum"])

    return {
        "retention": retention,
        "momentum": momentum,
        "health": health,
    }


__all__ = [
    "CohortPerformance",
    "build_insight_summary",
    "calculate_momentum",
    "calculate_retention",
    "generate_product_health_index",
]
