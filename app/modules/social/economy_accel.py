"""
Thin Python wrapper for the Rust-accelerated social economy routines.

If the compiled PyO3 extension `social_economy_rs` is available (built via maturin),
these functions will dispatch to Rust; otherwise they fall back to the existing Python logic.
"""

from __future__ import annotations

try:
    import social_economy_rs as _accel

    AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _accel = None
    AVAILABLE = False


def engagement_score(likes: int, comments: int) -> float:
    """Helper for engagement score."""
    if AVAILABLE:
        return float(_accel.engagement_score(int(likes), int(comments)))  # type: ignore[attr-defined]
    raw = (likes * 1) + (comments * 2)
    if raw <= 0:
        return 0.0
    import math

    return min(100.0, math.log(raw + 1) * 20)


def quality_score(content: str) -> float:
    """Helper for quality score."""
    if AVAILABLE:
        return float(_accel.quality_score(content))  # type: ignore[attr-defined]
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
    if words:
        diversity_ratio = len(unique_words) / len(words)
        if diversity_ratio > 0.6:
            score += 30
        elif diversity_ratio > 0.4:
            score += 15
    score += 20
    return min(100.0, score)
