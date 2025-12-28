from datetime import datetime, timedelta, timezone

import pytest
from fastapi import BackgroundTasks, HTTPException

from app import models, schemas
from types import SimpleNamespace

from app.services.comments.service import CommentService


def _service(session, monkeypatch):
    # minimize side effects
    monkeypatch.setattr(
        "app.services.comments.service.notifications",
        SimpleNamespace(manager=SimpleNamespace(broadcast=lambda *a, **k: None)),
    )
    monkeypatch.setattr("app.services.comments.service.queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.create_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.check_content_against_rules", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.check_for_profanity", lambda *a, **k: False)
    monkeypatch.setattr("app.services.comments.service.validate_urls", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.analyze_sentiment", lambda *a, **k: 0.0)
    monkeypatch.setattr("app.services.comments.service.is_valid_image_url", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.is_valid_video_url", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.detect_language", lambda *a, **k: "en")
    monkeypatch.setattr("app.services.comments.service.SocialEconomyService", lambda db: type("S", (), {"update_post_score": lambda *_: None})())
    return CommentService(session)


def test_create_and_delete_comment_updates_counts(session, monkeypatch):
    user = models.User(email="c21@example.com", hashed_password="x", is_verified=True, comment_count=0)
    post = models.Post(title="t", content="c", owner=user, comment_count=0)
    session.add_all([user, post])
    session.commit()
    session.refresh(user)
    session.refresh(post)

    service = _service(session, monkeypatch)
    payload = schemas.CommentCreate(post_id=post.id, parent_id=None, content="hello", image_url=None, video_url=None, sticker_id=None)
    comment = asyncio_run(
        service.create_comment(
            schema=payload,
            current_user=user,
            background_tasks=BackgroundTasks(),
            notification_module=SimpleNamespace(manager=SimpleNamespace(broadcast=lambda *a, **k: None)),
        )
    )
    session.refresh(user)
    session.refresh(post)
    assert user.comment_count == 1
    assert post.comment_count == 1

    resp = service.delete_comment(comment_id=comment.id, current_user=user)
    assert resp["message"] == "Comment deleted successfully"
    deleted = session.get(models.Comment, comment.id)
    assert deleted.is_deleted is True
    assert deleted.content == "[Deleted]"


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def test_update_comment_respects_owner_and_window(session, monkeypatch):
    user = models.User(email="c21b@example.com", hashed_password="x", is_verified=True)
    other = models.User(email="c21c@example.com", hashed_password="x", is_verified=True)
    post = models.Post(title="t", content="c", owner=user)
    session.add_all([user, other, post])
    session.commit()
    comment = models.Comment(
        owner_id=user.id,
        post_id=post.id,
        content="orig",
        language="en",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(comment)
    session.commit()

    service = _service(session, monkeypatch)
    with pytest.raises(HTTPException):
        service.update_comment(comment_id=comment.id, payload=schemas.CommentUpdate(content="x"), current_user=other, edit_window=timedelta(minutes=5))

    updated = service.update_comment(comment_id=comment.id, payload=schemas.CommentUpdate(content="edited"), current_user=user, edit_window=timedelta(days=1))
    assert updated.is_edited is True
    assert updated.content == "edited"
    history = session.query(models.CommentEditHistory).filter_by(comment_id=comment.id).all()
    assert history


def test_best_answer_and_highlight_flags(session, monkeypatch):
    user = models.User(email="c21d@example.com", hashed_password="x", is_verified=True)
    post = models.Post(title="t", content="c", owner=user)
    session.add_all([user, post])
    session.commit()
    comment = models.Comment(owner_id=user.id, post_id=post.id, content="first", language="en")
    session.add(comment)
    session.commit()

    service = _service(session, monkeypatch)
    # best answer toggle
    marked = service.set_best_answer(comment_id=comment.id, current_user=user)
    assert marked.is_best_answer is True
    # highlight toggle
    highlighted = service.toggle_highlight(comment_id=comment.id, current_user=user)
    assert highlighted.is_highlighted is True


def test_get_replies_sorted(session, monkeypatch):
    user = models.User(email="c21e@example.com", hashed_password="x", is_verified=True)
    post = models.Post(title="t", content="c", owner=user)
    session.add_all([user, post])
    session.commit()
    parent = models.Comment(owner_id=user.id, post_id=post.id, content="parent", language="en")
    session.add(parent)
    session.commit()
    reply1 = models.Comment(owner_id=user.id, post_id=post.id, content="r1", parent_id=parent.id, likes_count=5, language="en")
    reply2 = models.Comment(owner_id=user.id, post_id=post.id, content="r2", parent_id=parent.id, likes_count=1, language="en")
    session.add_all([reply1, reply2])
    session.commit()

    service = _service(session, monkeypatch)
    replies = service.list_replies(
        comment_id=parent.id,
        current_user=user,
        sort_by="likes_count",
        sort_order="desc",
    )
    assert replies[0].likes_count >= replies[1].likes_count


def test_toggle_pin_respects_owner_or_moderator(session, monkeypatch):
    owner = models.User(email="owner21@example.com", hashed_password="x", is_verified=True)
    commenter = models.User(email="comm21@example.com", hashed_password="x", is_verified=True)
    outsider = models.User(email="out21@example.com", hashed_password="x", is_verified=True)
    post = models.Post(title="t", content="c", owner=owner)
    session.add_all([owner, commenter, outsider, post])
    session.commit()
    comment = models.Comment(owner_id=commenter.id, post_id=post.id, content="hello", language="en")
    session.add(comment)
    session.commit()

    service = _service(session, monkeypatch)
    pinned = service.toggle_pin(comment_id=comment.id, current_user=owner)
    assert pinned.is_pinned is True
    assert pinned.pinned_at is not None

    with pytest.raises(HTTPException):
        service.toggle_pin(comment_id=comment.id, current_user=outsider)


def test_report_flags_profanity_sets_flag_reason(session, monkeypatch):
    user = models.User(email="flag21@example.com", hashed_password="x", is_verified=True)
    post = models.Post(title="t", content="c", owner=user)
    session.add_all([user, post])
    session.commit()
    comment = models.Comment(owner_id=user.id, post_id=post.id, content="bad http://evil.com", language="en")
    session.add(comment)
    session.commit()

    # enable profanity/url detection but keep other side effects muted
    monkeypatch.setattr("app.services.comments.service.check_for_profanity", lambda text: True)
    monkeypatch.setattr("app.services.comments.service.validate_urls", lambda text: False)
    monkeypatch.setattr(
        "app.services.comments.service.notifications",
        SimpleNamespace(manager=SimpleNamespace(broadcast=lambda *a, **k: None)),
    )
    monkeypatch.setattr("app.services.comments.service.queue_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.schedule_email_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.create_notification", lambda *a, **k: None)
    monkeypatch.setattr("app.services.comments.service.check_content_against_rules", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.analyze_sentiment", lambda *a, **k: 0.0)
    monkeypatch.setattr("app.services.comments.service.is_valid_image_url", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.is_valid_video_url", lambda *a, **k: True)
    monkeypatch.setattr("app.services.comments.service.detect_language", lambda *a, **k: "en")
    monkeypatch.setattr("app.services.comments.service.SocialEconomyService", lambda db: type("S", (), {"update_post_score": lambda *_: None})())
    service = CommentService(session)

    report = service.report_content(
        current_user=user,
        payload=SimpleNamespace(post_id=None, comment_id=comment.id, report_reason="spam"),
    )
    session.refresh(comment)
    assert report.ai_detected is True
    assert comment.is_flagged is True
    assert comment.flag_reason == "Automatic content check"
