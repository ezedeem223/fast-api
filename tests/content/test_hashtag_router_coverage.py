"""Additional coverage for hashtag router analytics paths."""

import warnings

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SAWarning

from app import models
from app.routers import hashtag as hashtag_router


def _make_user(session, email="h@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_hashtag(session, name):
    tag = models.Hashtag(name=name)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


def _make_post(session, owner_id, title, hashtags=None):
    post = models.Post(
        owner_id=owner_id, title=title, content="c", is_safe_content=True
    )
    if hashtags:
        post.hashtags = hashtags
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def test_get_hashtags_and_follow_unfollow_errors(session):
    """List hashtags and verify follow/unfollow error branches."""
    user = _make_user(session)
    tag = _make_hashtag(session, "fastapi")

    tags = hashtag_router.get_hashtags(db=session)
    assert len(tags) == 1

    # Already following branch
    user.followed_hashtags.append(tag)
    session.commit()
    with pytest.raises(HTTPException) as exc:
        hashtag_router.follow_hashtag(tag.id, db=session, current_user=user)
    assert exc.value.status_code == 400

    # Not following branch
    user.followed_hashtags.clear()
    session.commit()
    with pytest.raises(HTTPException) as exc2:
        hashtag_router.unfollow_hashtag(tag.id, db=session, current_user=user)
    assert exc2.value.status_code == 400


def test_trending_hashtags_and_posts_by_hashtag(session):
    """Trending and posts-by-hashtag endpoints return expected data."""
    user = _make_user(session, email="trend@example.com")
    tag1 = _make_hashtag(session, "python")
    tag2 = _make_hashtag(session, "fastapi")

    _make_post(session, user.id, "p1", hashtags=[tag1])
    _make_post(session, user.id, "p2", hashtags=[tag1])
    _make_post(session, user.id, "p3", hashtags=[tag2])

    trending = hashtag_router.get_trending_hashtags(db=session, limit=2)
    assert trending[0].name == "python"

    posts = hashtag_router.get_posts_by_hashtag("fastapi", db=session)
    assert len(posts) == 1

    with pytest.raises(HTTPException) as exc:
        hashtag_router.get_posts_by_hashtag("missing", db=session)
    assert exc.value.status_code == 404


def test_hashtag_statistics_and_engagement_rate(session, monkeypatch):
    """Statistics counts followers/posts and engagement rate."""
    user = _make_user(session, email="stats@example.com")
    follower = _make_user(session, email="follower@example.com")
    tag = _make_hashtag(session, "stats")
    follower.followed_hashtags.append(tag)
    session.commit()

    class DummyVote:
        id = hashtag_router.models.Comment.id

    monkeypatch.setattr(hashtag_router.models, "Vote", DummyVote)
    post = _make_post(session, user.id, "stat-post", hashtags=[tag])
    comment = models.Comment(post_id=post.id, owner_id=user.id, content="hi")
    session.add(comment)
    session.commit()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SAWarning)
        stats = hashtag_router.get_hashtag_statistics(
            tag.id, db=session, current_user=user
        )
    assert stats.post_count == 1
    assert stats.follower_count == 1
    assert stats.engagement_rate == 2.0

    with pytest.raises(HTTPException) as exc:
        hashtag_router.get_hashtag_statistics(9999, db=session, current_user=user)
    assert exc.value.status_code == 404


def test_hashtag_statistics_zero_posts_returns_zero_rate(session, monkeypatch):
    """Engagement rate falls back to 0 when no posts exist."""
    user = _make_user(session, email="zero@example.com")
    tag = _make_hashtag(session, "empty")

    class DummyVote:
        id = hashtag_router.models.Comment.id

    monkeypatch.setattr(hashtag_router.models, "Vote", DummyVote)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SAWarning)
        stats = hashtag_router.get_hashtag_statistics(
            tag.id, db=session, current_user=user
        )
    assert stats.post_count == 0
    assert stats.engagement_rate == 0.0
