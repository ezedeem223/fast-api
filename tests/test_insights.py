"""Unit tests for the growth and retention insights helpers and API."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.insights import CohortPerformance, build_insight_summary, calculate_retention, generate_product_health_index
from app.main import _include_routers, create_application


@pytest.fixture()
def insights_client():
    """Provide a FastAPI client with the insights router loaded."""

    app = create_application()
    _include_routers(app)
    with TestClient(app) as client:
        yield client


def test_calculate_retention_produces_average():
    """Retention helper should expose per-cohort rates and an overall mean."""

    cohorts = [
        CohortPerformance(date(2024, 1, 1), size=100, returning=70),
        CohortPerformance(date(2024, 2, 1), size=80, returning=40),
    ]
    summary = calculate_retention(cohorts)
    assert pytest.approx(summary["average_retention"], rel=1e-3) == 0.6
    assert summary["cohorts"][0]["retention_rate"] == 0.7


def test_generate_product_health_index_ranks_features():
    """Product health score should highlight the most adopted features."""

    feature_usage = {"stories": 400, "live": 150, "audio_rooms": 50}
    score = generate_product_health_index(feature_usage, sentiment_score=0.7, momentum_score=0.8)
    assert score["feature_focus"][0]["feature"] == "stories"
    assert score["health_score"] == pytest.approx(0.76, rel=1e-3)


def test_build_insight_summary_combines_metrics():
    """Full insight summary should include retention, momentum, and health."""

    cohorts = [
        CohortPerformance(date(2024, 3, 1), 120, 90),
        CohortPerformance(date(2024, 4, 1), 100, 60),
    ]
    summary = build_insight_summary(
        cohorts=cohorts,
        daily_active_users=[320, 340, 360],
        new_signups=[80, 90, 85],
        churned_users=[20, 25, 18],
        feature_usage={"stories": 500, "live": 200},
        sentiment_score=0.65,
    )
    assert "retention" in summary and "momentum" in summary and "health" in summary
    assert summary["retention"]["cohorts"][1]["retention_rate"] == pytest.approx(0.6, rel=1e-3)
    assert summary["momentum"]["growth_rate"] > 0


def test_insights_summary_endpoint_returns_feedback_average(insights_client):
    """API should aggregate feedback sentiment and return structured summary."""

    payload = {
        "daily_active_users": [200, 220, 240],
        "new_signups": [60, 65, 70],
        "churned_users": [10, 12, 11],
        "feature_usage": {"stories": 320, "live": 140, "audio_rooms": 60},
        "cohorts": [
            {"start_date": "2024-01-01", "size": 150, "returning": 105},
            {"start_date": "2024-02-01", "size": 130, "returning": 78},
        ],
        "sentiment_score": 0.5,
        "feedback_samples": [
            "The stories feature is excellent and great",
            "The live rooms feel bad and terrible",
        ],
    }
    response = insights_client.post("/insights/summary", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["feedback"]["sample_count"] == 2
    assert data["feedback"]["average_sentiment"] == pytest.approx(0.6, rel=1e-3)
    assert data["health"]["feature_focus"][0]["feature"] == "stories"


def test_insights_momentum_endpoint_exposes_breakdown(insights_client):
    """Momentum endpoint should return all sub-metrics for dashboards."""

    payload = {
        "daily_active_users": [120, 150, 180, 210],
        "new_signups": [40, 45, 50, 55],
        "churned_users": [10, 12, 14, 16],
        "feature_usage": {},
        "cohorts": [],
    }
    response = insights_client.post("/insights/momentum", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert {"growth_rate", "activation_ratio", "volatility_penalty", "momentum"} <= data.keys()
    assert data["growth_rate"] > 0
