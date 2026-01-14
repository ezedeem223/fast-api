"""Extra coverage for PostService helper paths."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import models
from app.modules.posts import schemas as post_schemas
from app.modules.posts.models import PostRelation
from app.services.posts import post_service
from app.services.posts.post_service import PostService
from fastapi import HTTPException


def _user(session, email: str) -> models.User:
    user = models.User(email=email, hashed_password="x", is_verified=True)
    user.username = email.split("@")[0]
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _payload(**kwargs) -> post_schemas.PostCreate:
    base = dict(
        title="Title",
        content="Some content",
        hashtags=[],
        analyze_content=False,
    )
    base.update(kwargs)
    return post_schemas.PostCreate(**base)


def test_create_post_analyze_and_offensive(session, monkeypatch):
    user = _user(session, "author@example.com")
    service = PostService(session)

    monkeypatch.setattr(post_service, "check_content", lambda *a, **k: ([], []))
    monkeypatch.setattr(post_service, "filter_content", lambda *a, **k: "filtered")
    monkeypatch.setattr(post_service, "process_mentions", lambda *a, **k: [])
    monkeypatch.setattr(post_service, "is_content_offensive", lambda *a, **k: (True, 0.8))

    class DummyEconomy:
        def __init__(self, db):
            self.db = db

        def update_post_score(self, post_id):
            return 1.0

        def check_and_award_badges(self, user_id):
            return None

    monkeypatch.setattr(post_service, "SocialEconomyService", DummyEconomy)

    analysis = {
        "sentiment": {"sentiment": "positive", "score": 0.7},
        "suggestion": "ok",
    }

    post = service.create_post(
        background_tasks=SimpleNamespace(add_task=lambda *args, **kwargs: None),
        payload=_payload(analyze_content=True),
        current_user=user,
        queue_email_fn=lambda *args, **kwargs: None,
        schedule_email_fn=lambda *args, **kwargs: None,
        broadcast_fn=lambda *args, **kwargs: None,
        share_on_twitter_fn=lambda *args, **kwargs: None,
        share_on_facebook_fn=lambda *args, **kwargs: None,
        mention_notifier_fn=lambda *args, **kwargs: None,
        analyze_content_fn=lambda *args, **kwargs: analysis,
    )

    created = session.get(models.Post, post.id)
    assert created.is_flagged is True
    assert created.sentiment == "positive"
    assert created.is_published is True


def test_create_post_banned_and_missing_community(session, monkeypatch):
    user = _user(session, "author2@example.com")
    service = PostService(session)

    monkeypatch.setattr(post_service, "check_content", lambda *a, **k: ([], ["ban"]))
    monkeypatch.setattr(post_service, "filter_content", lambda *a, **k: "filtered")
    with pytest.raises(HTTPException):
        service.create_post(
            background_tasks=SimpleNamespace(add_task=lambda *args, **kwargs: None),
            payload=_payload(),
            current_user=user,
            queue_email_fn=lambda *args, **kwargs: None,
            schedule_email_fn=lambda *args, **kwargs: None,
            broadcast_fn=lambda *args, **kwargs: None,
            share_on_twitter_fn=lambda *args, **kwargs: None,
            share_on_facebook_fn=lambda *args, **kwargs: None,
            mention_notifier_fn=lambda *args, **kwargs: None,
        )

    monkeypatch.setattr(post_service, "check_content", lambda *a, **k: ([], []))
    with pytest.raises(HTTPException):
        service.create_post(
            background_tasks=SimpleNamespace(add_task=lambda *args, **kwargs: None),
            payload=_payload(community_id=999),
            current_user=user,
            queue_email_fn=lambda *args, **kwargs: None,
            schedule_email_fn=lambda *args, **kwargs: None,
            broadcast_fn=lambda *args, **kwargs: None,
            share_on_twitter_fn=lambda *args, **kwargs: None,
            share_on_facebook_fn=lambda *args, **kwargs: None,
            mention_notifier_fn=lambda *args, **kwargs: None,
        )


@pytest.mark.asyncio
async def test_post_mentions_list_and_translation(session, monkeypatch):
    user = _user(session, "mentioner@example.com")
    mentionee = _user(session, "mentionee@example.com")

    post = models.Post(owner_id=user.id, title="Hello", content="c", is_archived=False)
    post.mentioned_users.append(mentionee)
    session.add(post)
    session.commit()
    session.refresh(post)

    service = PostService(session)
    results = service.get_posts_with_mentions(
        current_user=mentionee,
        skip=0,
        limit=10,
        search="Hell",
        include_archived=False,
    )
    assert results

    monkeypatch.setenv("ENABLE_TRANSLATION", "1")

    async def _translator(*args, **kwargs):
        raise TypeError("no translation")

    translated = await service.list_posts(
        current_user=mentionee,
        limit=5,
        skip=0,
        search="",
        translate=True,
        translator_fn=_translator,
    )
    assert translated


def test_living_memory_timeline_and_exports(session, monkeypatch):
    user = _user(session, "memory@example.com")
    service = PostService(session)

    now = datetime.now(timezone.utc)
    try:
        older_date = now.replace(year=now.year - 1)
    except ValueError:
        older_date = now - timedelta(days=365)

    older = models.Post(
        owner_id=user.id,
        title="Older",
        content="shared memory words",
        created_at=older_date,
    )
    newer = models.Post(
        owner_id=user.id,
        title="Newer",
        content="shared memory words again",
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([older, newer])
    session.commit()
    session.refresh(older)
    session.refresh(newer)

    service._process_living_memory(session, newer, user.id)
    relations = session.query(PostRelation).filter_by(source_post_id=newer.id).all()
    assert relations

    timeline = service.get_user_timeline(user.id)
    assert timeline

    memories = service.get_on_this_day_memories(user.id)
    assert memories

    monkeypatch.setattr(post_service, "_create_pdf", lambda post: BytesIO(b"pdf"))
    assert service.export_post_as_pdf(post_id=newer.id) == b"pdf"

    monkeypatch.setattr(post_service, "_create_pdf", lambda post: None)
    with pytest.raises(HTTPException):
        service.export_post_as_pdf(post_id=newer.id)
