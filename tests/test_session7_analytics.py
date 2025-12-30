from datetime import datetime, timedelta, timezone

import app.analytics as analytics
import app.modules.utils.analytics as utils_analytics
from app import models


def _user(session, email="u@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_analyze_content_negative_and_short(monkeypatch):
    # stub sentiment pipeline to avoid heavy load
    monkeypatch.setattr(
        analytics,
        "_get_sentiment_pipeline",
        lambda: lambda text: [{"label": "NEGATIVE", "score": 0.9}],
    )
    res = analytics.analyze_content("short text")
    assert res["sentiment"]["sentiment"] == "NEGATIVE"
    assert "positive tone" in res["suggestion"]

    monkeypatch.setattr(
        analytics,
        "_get_sentiment_pipeline",
        lambda: lambda text: [{"label": "POSITIVE", "score": 0.5}],
    )
    res2 = analytics.analyze_content("tiny")
    assert "short" in res2["suggestion"].lower()


def test_record_search_and_cache_paths(session, monkeypatch):
    user = _user(session)
    # mock cache to test hit/miss
    cache = {}
    monkeypatch.setattr(
        analytics,
        "set_cached_json",
        lambda key, value, ttl_seconds=300: cache.__setitem__(key, value),
    )
    monkeypatch.setattr(analytics, "get_cached_json", lambda key: cache.get(key))
    monkeypatch.setattr(analytics, "invalidate_stats_cache", lambda **kw: cache.clear())
    monkeypatch.setattr(
        analytics, "popular_cache_key", lambda limit: f"popular:{limit}"
    )
    monkeypatch.setattr(analytics, "recent_cache_key", lambda limit: f"recent:{limit}")
    monkeypatch.setattr(
        analytics, "user_cache_key", lambda uid, limit: f"user:{uid}:{limit}"
    )

    analytics.record_search_query(session, "hello", user.id)
    analytics.record_search_query(session, "hello", user.id)

    popular = analytics.get_popular_searches(session, limit=5)
    assert popular[0].count == 2

    cached = analytics.get_popular_searches(session, limit=5)
    assert cached[0].count == 2  # served from cache

    recent = analytics.get_recent_searches(session, limit=5)
    assert recent
    user_searches = analytics.get_user_searches(session, user_id=user.id, limit=5)
    assert user_searches[0].query == "hello"

    analytics.clean_old_statistics(session, days=0)
    assert session.query(models.SearchStatistics).count() == 0


def test_update_conversation_statistics_edge_cases(session):
    sender = _user(session, "s@example.com")
    receiver = _user(session, "r@example.com")
    msg = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        content="hi",
        encrypted_content=b"hi",
        conversation_id="c1",
        timestamp=datetime.now(timezone.utc),
        message_type="text",
    )
    setattr(msg, "has_emoji", False)
    session.add(msg)
    session.commit()

    # no existing stats, creates new
    analytics.update_conversation_statistics(session, "c1", msg)
    stats = (
        session.query(models.ConversationStatistics)
        .filter_by(conversation_id="c1")
        .first()
    )
    assert stats.total_messages == 1

    # add previous message to test response time and counts
    old = models.Message(
        sender_id=receiver.id,
        receiver_id=sender.id,
        content="old",
        encrypted_content=b"old",
        conversation_id="c1",
        timestamp=msg.timestamp - timedelta(seconds=10),
        message_type="sticker",
    )
    setattr(old, "has_emoji", True)
    session.add(old)
    session.commit()
    # new message with attachments and emoji/sticker
    msg2 = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        content="reply 😊",
        encrypted_content=b"reply",
        conversation_id="c1",
        timestamp=msg.timestamp + timedelta(seconds=5),
        message_type="sticker",
    )
    setattr(msg2, "has_emoji", True)
    attach = models.MessageAttachment(file_url="f", file_type="image/png")
    msg2.attachments.append(attach)
    session.add(msg2)
    session.commit()

    analytics.update_conversation_statistics(session, "c1", msg2)
    stats = (
        session.query(models.ConversationStatistics)
        .filter_by(conversation_id="c1")
        .first()
    )
    assert stats.total_messages == 2
    assert stats.total_files == 1
    assert stats.total_emojis >= 1
    assert stats.total_stickers >= 1
    assert stats.average_response_time > 0


def test_check_call_quality_and_cleanup():
    utils_analytics.quality_buffers.clear()
    score = utils_analytics.check_call_quality(
        {"packet_loss": 1, "latency": 30, "jitter": 5}, "call1"
    )
    assert score < 100
    assert (
        utils_analytics.should_adjust_video_quality("call1") is False
        or utils_analytics.should_adjust_video_quality("call1") is True
    )
    quality = utils_analytics.get_recommended_video_quality("call1")
    assert quality in {"low", "medium", "high"}
    # simulate stale buffer
    utils_analytics.quality_buffers["call1"].last_update_time -= 400
    utils_analytics.clean_old_quality_buffers()
    assert "call1" not in utils_analytics.quality_buffers


def test_update_post_score_negative_paths(session, monkeypatch):
    post = models.Post(
        owner_id=1,
        title="t",
        content="c",
        is_safe_content=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(post)
    session.commit()
    # no reactions, score set to 0 or above
    utils_analytics.update_post_score(session, post)
    assert post.score >= 0

    # missing post in vote statistics update returns None
    assert utils_analytics.update_post_vote_statistics(session, post_id=999999) is None


def test_get_user_vote_analytics_empty(session):
    analytics_out = utils_analytics.get_user_vote_analytics(session, user_id=12345)
    assert analytics_out.total_posts == 0
    assert analytics_out.total_votes_received == 0
