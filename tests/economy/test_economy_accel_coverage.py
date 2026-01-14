"""Targeted coverage tests for social economy acceleration fallbacks."""

from types import SimpleNamespace

from app.modules.social import economy_accel


def test_economy_accel_fallback_paths():
    economy_accel.AVAILABLE = False
    economy_accel._accel = None

    assert economy_accel.engagement_score(0, 0) == 0.0
    score = economy_accel.engagement_score(2, 1)
    assert score > 0.0

    text = ("word " * 60).strip() + "\nmore words"
    quality = economy_accel.quality_score(text)
    assert 0.0 < quality <= 100.0


def test_economy_accel_accelerated_paths():
    original_available = economy_accel.AVAILABLE
    original_accel = economy_accel._accel
    try:
        economy_accel._accel = SimpleNamespace(
            engagement_score=lambda likes, comments: 42,
            quality_score=lambda content: 88,
        )
        economy_accel.AVAILABLE = True
        assert economy_accel.engagement_score(1, 1) == 42.0
        assert economy_accel.quality_score("content") == 88.0
    finally:
        economy_accel.AVAILABLE = original_available
        economy_accel._accel = original_accel
