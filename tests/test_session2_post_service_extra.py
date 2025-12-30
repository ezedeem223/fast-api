import pytest

from app import models, schemas
from app.services.posts.post_service import PostService
from fastapi import BackgroundTasks, HTTPException


def _make_user(
    session, email: str, verified: bool = True, privacy="public"
) -> models.User:
    user = models.User(
        email=email, hashed_password="x", is_verified=verified, privacy_level=privacy
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_create_post_rejects_banned_words(session, monkeypatch):
    service = PostService(session)
    user = _make_user(session, "ban@example.com")
    tasks = BackgroundTasks()
    monkeypatch.setattr(
        "app.services.posts.post_service.check_content",
        lambda db, content: ([], ["bad"]),
    )
    monkeypatch.setattr(
        "app.services.posts.post_service.filter_content", lambda db, content: content
    )
    payload = schemas.PostCreate(title="t", content="bad")
    with pytest.raises(HTTPException):
        service.create_post(
            background_tasks=tasks,
            payload=payload,
            current_user=user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda msg: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
        )


def test_create_post_flags_offensive_content(session, monkeypatch):
    service = PostService(session)
    user = _make_user(session, "flag@example.com")
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
        "app.services.posts.post_service.is_content_offensive",
        lambda content: (True, 0.9),
    )

    payload = schemas.PostCreate(title="t", content="offensive text")
    post_out = service.create_post(
        background_tasks=tasks,
        payload=payload,
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
        schedule_email_fn=lambda *a, **k: None,
        broadcast_fn=lambda msg: None,
        share_on_twitter_fn=lambda *a, **k: None,
        share_on_facebook_fn=lambda *a, **k: None,
        mention_notifier_fn=lambda *a, **k: None,
    )
    db_post = session.get(models.Post, post_out.id)
    assert db_post.is_flagged is True
    assert "offensive" in (db_post.flag_reason or "").lower()


def test_prepare_post_response_sets_privacy_default(session):
    service = PostService(session)
    user = _make_user(session, "privacy@example.com", privacy="private")
    post = models.Post(owner_id=user.id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    session.refresh(post)
    post_out = service._prepare_post_response(post, owner=user)
    assert post_out.privacy_level == schemas.PrivacyLevel.PRIVATE
