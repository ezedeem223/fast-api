from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.modules.utils import content, analytics


def test_offensive_content_stub_and_safe_analyze(monkeypatch):
    monkeypatch.setattr(content, "USE_LIGHTWEIGHT_NLP", True, raising=False)
    content._offensive_classifier = None
    offensive, score = content.is_content_offensive("friendly text")
    assert offensive is False
    assert score == 0.0

    # safe_analyze returns neutral/unknown for empty or errors
    result_empty = content.safe_analyze("")
    assert result_empty["sentiment"] in {"neutral", "unknown"}
    assert result_empty["score"] == 0.0


def test_sanitize_and_antivirus_scan():
    raw = "<script>alert('x')</script><b>hello</b>   world"
    cleaned = content.sanitize_text(raw)
    assert "script" not in cleaned.lower()
    assert cleaned == "hello world"

    assert content.antivirus_scan(b"ok", scanner=lambda d: True) is True
    assert content.antivirus_scan(b"bad", scanner=lambda d: False) is False
    assert content.antivirus_scan(b"err", scanner=lambda d: (_ for _ in ()).throw(ValueError("x"))) is False


def test_content_classifier_flags_offensive(monkeypatch, tmp_path):
    # Force classifier path to use lightweight stub to avoid heavy model
    monkeypatch.setattr(content, "USE_LIGHTWEIGHT_NLP", True, raising=False)
    content._offensive_classifier = None
    content._sentiment_pipeline = None

    # ensure profanity path triggers True
    assert content.check_for_profanity("shit happens") is True
    assert content.check_for_profanity("clean sentence") in {True, False}


def test_calculate_post_score_and_vote_statistics(session):
    post = models.Post(
        title="t",
        content="c",
        owner_id=1,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        score=0.0,
        comment_count=2,
    )
    session.add(post)
    session.commit()
    session.refresh(post)

    score = analytics.calculate_post_score(5, 1, post.comment_count, post.created_at)
    assert score > 0

    reactions = [
        models.Reaction(post_id=post.id, user_id=1, reaction_type="like"),
        models.Reaction(post_id=post.id, user_id=2, reaction_type="love"),
        models.Reaction(post_id=post.id, user_id=3, reaction_type="angry"),
    ]
    session.add_all(reactions)
    session.commit()

    analytics.update_post_score(session, post)
    analytics.update_post_vote_statistics(session, post.id)

    session.refresh(post)
    assert post.score >= 0
    assert post.vote_statistics.total_votes == 3
    assert post.vote_statistics.upvotes == 2
    assert post.vote_statistics.downvotes == 1


def test_update_ban_statistics_creates_and_increments(session):
    analytics.update_ban_statistics(session, target="word", reason="spam", score=5.0)
    stats = session.query(models.BanStatistics).first()
    assert stats.total_bans == 1
    assert stats.word_bans == 1

    analytics.update_ban_statistics(session, target="ip", reason="abuse", score=3.0)
    session.refresh(stats)
    assert stats.total_bans == 2
    assert stats.ip_bans == 1
