from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest

from app import models, schemas
from app.modules.posts.models import PostRelation
from app.modules.utils.security import hash as hash_password
from app.services.posts.post_service import PostService
from fastapi import BackgroundTasks, HTTPException, UploadFile


def _user(session, email="post@example.com", verified=True, privacy="public"):
    user = models.User(
        email=email,
        hashed_password=hash_password("x"),
        is_verified=verified,
        privacy_level=privacy,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class _StubSocialEconomy:
    def __init__(self):
        self.awarded = False

    def update_post_score(self, post_id):
        return 1

    def check_and_award_badges(self, user_id):
        self.awarded = True


class _StubScheduler:
    def __init__(self):
        self.called_with = None

    def apply_async(self, args=None, eta=None):
        self.called_with = (args, eta)


def _no_ops():
    return (
        lambda *a, **k: None,
        lambda *a, **k: None,
        lambda *a, **k: None,
        lambda *a, **k: None,
        lambda *a, **k: None,
        lambda *a, **k: None,
    )


def _post_create_payload(**overrides):
    data = {
        "title": "t",
        "content": "content body",
        "hashtags": [],
        "community_id": None,
        "is_help_request": False,
        "scheduled_time": None,
        "category_id": None,
        "related_to_post_id": None,
        "relation_type": None,
        "is_living_testimony": False,
        "analyze_content": False,
        "copyright_type": schemas.CopyrightType.ALL_RIGHTS_RESERVED,
        "custom_copyright": "",
        "is_encrypted": False,
        "encryption_key_id": None,
    }
    data.update(overrides)
    return schemas.PostCreate(**data)


def test_create_post_requires_verification_and_nonempty(session, monkeypatch):
    service = PostService(session)
    tasks = BackgroundTasks()
    unverified = _user(session, verified=False)
    verified = _user(session, email="ok@example.com")

    queue_email_fn, schedule_email_fn, broadcast_fn, share_tw, share_fb, notify = (
        _no_ops()
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.check_content", lambda db, content: ([], [])
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content", lambda db, content: content
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.process_mentions", lambda content, db: []
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.get_or_create_hashtag",
        lambda db, name: models.Hashtag(name=name),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.SocialEconomyService", _StubSocialEconomy
    )

    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=tasks,
            payload=_post_create_payload(),
            current_user=unverified,
            queue_email_fn=queue_email_fn,
            schedule_email_fn=schedule_email_fn,
            broadcast_fn=broadcast_fn,
            share_on_twitter_fn=share_tw,
            share_on_facebook_fn=share_fb,
            mention_notifier_fn=notify,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=tasks,
            payload=_post_create_payload(content="   "),
            current_user=verified,
            queue_email_fn=queue_email_fn,
            schedule_email_fn=schedule_email_fn,
            broadcast_fn=broadcast_fn,
            share_on_twitter_fn=share_tw,
            share_on_facebook_fn=share_fb,
            mention_notifier_fn=notify,
        )
    assert exc.value.status_code == 422


def test_create_post_scheduled_with_analysis_and_scheduler(session, monkeypatch):
    service = PostService(session)
    user = _user(session, email="sched@example.com")
    tasks = BackgroundTasks()
    scheduler = _StubScheduler()
    monkeypatch.setattr(
        "app.services.posts.post_service.schedule_post_publication", scheduler
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.check_content", lambda db, content: ([], [])
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content",
        lambda db, content: content + " clean",
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.process_mentions", lambda content, db: []
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.get_or_create_hashtag",
        lambda db, name: models.Hashtag(name=name),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.SocialEconomyService", _StubSocialEconomy
    )

    queue_email_fn, schedule_email_fn, broadcast_fn, share_tw, share_fb, notify = (
        _no_ops()
    )

    analyze_result = {
        "sentiment": {"sentiment": "positive", "score": 0.8},
        "suggestion": "keep writing",
    }
    payload = _post_create_payload(
        scheduled_time=datetime.now(timezone.utc) + timedelta(hours=1),
        analyze_content=True,
        hashtags=["news"],
    )
    post_out = service.create_post(
        background_tasks=tasks,
        payload=payload,
        current_user=user,
        queue_email_fn=queue_email_fn,
        schedule_email_fn=schedule_email_fn,
        broadcast_fn=broadcast_fn,
        share_on_twitter_fn=share_tw,
        share_on_facebook_fn=share_fb,
        mention_notifier_fn=notify,
        analyze_content_fn=lambda content: analyze_result,
    )

    db_post = session.get(models.Post, post_out.id)
    assert db_post.is_published is False
    assert db_post.sentiment == "positive"
    assert db_post.sentiment_score == 0.8
    assert db_post.content.endswith("clean")
    assert scheduler.called_with[0][0] == db_post.id


def test_create_post_analyze_flag_without_fn_raises(session, monkeypatch):
    service = PostService(session)
    user = _user(session, email="missing@example.com")
    tasks = BackgroundTasks()
    monkeypatch.setattr(
        "app.services.posts.post_service.check_content", lambda db, content: ([], [])
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content", lambda db, content: content
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.process_mentions", lambda content, db: []
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.get_or_create_hashtag",
        lambda db, name: models.Hashtag(name=name),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.SocialEconomyService", _StubSocialEconomy
    )

    queue_email_fn, schedule_email_fn, broadcast_fn, share_tw, share_fb, notify = (
        _no_ops()
    )
    payload = _post_create_payload(analyze_content=True)
    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=tasks,
            payload=payload,
            current_user=user,
            queue_email_fn=queue_email_fn,
            schedule_email_fn=schedule_email_fn,
            broadcast_fn=broadcast_fn,
            share_on_twitter_fn=share_tw,
            share_on_facebook_fn=share_fb,
            mention_notifier_fn=notify,
        )
    assert exc.value.status_code == 500


def test_toggle_allow_reposts_and_archive_permissions(session):
    service = PostService(session)
    owner = _user(session, "owner@example.com")
    other = _user(session, "other@example.com")
    post = models.Post(owner_id=owner.id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        service.toggle_allow_reposts(post_id=post.id, current_user=other)
    assert exc.value.status_code == 403

    toggled = service.toggle_allow_reposts(post_id=post.id, current_user=owner)
    assert toggled.id == post.id
    assert session.get(models.Post, post.id).allow_reposts is False

    archived = service.toggle_archive_post(post_id=post.id, current_user=owner)
    assert archived.is_archived is True
    assert session.get(models.Post, post.id).archived_at is not None


def test_update_post_success_and_permissions(session, monkeypatch):
    service = PostService(session)
    owner = _user(session, "owner2@example.com")
    other = _user(session, "other2@example.com")
    post = models.Post(
        owner_id=owner.id, title="old", content="old c", is_safe_content=True
    )
    session.add(post)
    session.commit()

    payload = _post_create_payload(
        title="new",
        content="new content with #tag",
        hashtags=["tag"],
        analyze_content=True,
        copyright_type=schemas.CopyrightType.PUBLIC_DOMAIN,
        custom_copyright="cc",
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.process_mentions", lambda content, db: [other]
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.get_or_create_hashtag",
        lambda db, name: models.Hashtag(name=name),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.check_content", lambda db, content: ([], [])
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content", lambda db, content: content
    )

    analysis = {"sentiment": {"sentiment": "neutral", "score": 0.5}, "suggestion": "ok"}

    with pytest.raises(HTTPException) as exc:
        service.update_post(
            post_id=post.id,
            payload=payload,
            current_user=other,
            analyze_content_fn=lambda c: analysis,
        )
    assert exc.value.status_code == 403

    updated = service.update_post(
        post_id=post.id,
        payload=payload,
        current_user=owner,
        analyze_content_fn=lambda c: analysis,
    )
    db_post = session.get(models.Post, post.id)
    assert db_post.content.startswith("new content")
    assert db_post.sentiment == "neutral"
    assert db_post.custom_copyright == "cc"
    assert len(db_post.mentioned_users) == 1
    assert updated.sentiment == "neutral"


def test_create_poll_vote_and_results(session):
    service = PostService(session)
    user = _user(session, "poll@example.com")
    tasks = BackgroundTasks()

    poll_out = service.create_poll_post(
        background_tasks=tasks,
        payload=schemas.PollCreate(
            title="poll", description="d", options=["a", "b"], end_date=None
        ),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
    )
    options = (
        session.query(models.PollOption)
        .filter(models.PollOption.post_id == poll_out.id)
        .all()
    )
    assert len(options) == 2

    res = service.vote_in_poll(
        post_id=poll_out.id, option_id=options[0].id, current_user=user
    )
    assert res["message"].startswith("Vote")

    with pytest.raises(HTTPException) as exc:
        service.vote_in_poll(post_id=poll_out.id, option_id=999999, current_user=user)
    assert exc.value.status_code == 404

    expired_poll = service.create_poll_post(
        background_tasks=tasks,
        payload=schemas.PollCreate(
            title="poll2",
            description="d2",
            options=["x", "y"],
            end_date=datetime.now() - timedelta(days=1),
        ),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
    )
    expired_option = (
        session.query(models.PollOption)
        .filter(models.PollOption.post_id == expired_poll.id)
        .first()
    )
    with pytest.raises(HTTPException) as exc:
        service.vote_in_poll(
            post_id=expired_poll.id, option_id=expired_option.id, current_user=user
        )
    assert exc.value.status_code == 400

    results = service.get_poll_results(post_id=poll_out.id)
    assert results["total_votes"] >= 1
    assert "percentage" in results["results"][0]


def test_report_content_delegates(session, monkeypatch):
    service = PostService(session)
    user = _user(session, "report@example.com")
    captured = {}
    monkeypatch.setattr(
        "app.services.posts.post_service.submit_report",
        lambda db, current_user, **kwargs: captured.update(kwargs) or {"ok": True},
    )
    resp = service.report_content(
        current_user=user, reason="spam", post_id=1, comment_id=None
    )
    assert resp["ok"] is True
    assert captured["reason"] == "spam"
    assert captured["post_id"] == 1


def test_living_memory_relation_created(session, monkeypatch):
    service = PostService(session)
    user = _user(session, "memory2@example.com")
    old = models.Post(
        owner_id=user.id,
        title="old",
        content="hello world memory",
        is_safe_content=True,
    )
    session.add(old)
    session.commit()

    monkeypatch.setattr(
        "app.services.posts.post_service.check_content", lambda db, content: ([], [])
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content", lambda db, content: content
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.process_mentions", lambda content, db: []
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.get_or_create_hashtag",
        lambda db, name: models.Hashtag(name=name),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.SocialEconomyService", _StubSocialEconomy
    )

    new_post_out = service.create_post(
        background_tasks=BackgroundTasks(),
        payload=_post_create_payload(content="hello world brand new memory"),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
        schedule_email_fn=lambda *a, **k: None,
        broadcast_fn=lambda *a, **k: None,
        share_on_twitter_fn=lambda *a, **k: None,
        share_on_facebook_fn=lambda *a, **k: None,
        mention_notifier_fn=lambda *a, **k: None,
    )
    rel = (
        session.query(PostRelation)
        .filter(
            PostRelation.source_post_id == new_post_out.id,
            PostRelation.target_post_id == old.id,
        )
        .first()
    )
    assert rel is not None
