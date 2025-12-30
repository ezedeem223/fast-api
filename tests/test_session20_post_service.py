from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.modules.posts import schemas as post_schemas
from app.services.posts import post_service
from app.services.posts.post_service import PostService
from fastapi import BackgroundTasks, HTTPException


def _stubbed_service(session, monkeypatch, cache_hits):
    # neutralize heavy checks
    monkeypatch.setattr(post_service, "check_content", lambda db, c: ([], []))
    monkeypatch.setattr(post_service, "filter_content", lambda db, c: c)
    monkeypatch.setattr(post_service, "is_content_offensive", lambda text: (False, 0.0))
    monkeypatch.setattr(
        post_service.cache_manager,
        "invalidate_nowait",
        lambda key: cache_hits.append(key),
    )
    return PostService(session)


def test_create_post_increments_count_and_invalidates_cache(session, monkeypatch):
    user = models.User(
        email="p20@example.com", hashed_password="x", is_verified=True, post_count=0
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    cache_hits = []
    service = _stubbed_service(session, monkeypatch, cache_hits)
    payload = post_schemas.PostCreate(
        title="hello",
        content="world",
        published=True,
        hashtags=[],
    )
    created = service.create_post(
        background_tasks=BackgroundTasks(),
        payload=payload,
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
        schedule_email_fn=lambda *a, **k: None,
        broadcast_fn=lambda *a, **k: None,
        share_on_twitter_fn=lambda *a, **k: None,
        share_on_facebook_fn=lambda *a, **k: None,
        mention_notifier_fn=lambda *a, **k: None,
        analyze_content_fn=None,
    )
    updated_user = session.get(models.User, user.id)
    assert updated_user.post_count == 1
    assert created.title == "hello"
    assert any(key.startswith("posts:list") for key in cache_hits)


def test_update_post_forbidden_for_non_owner(session, monkeypatch):
    owner = models.User(
        email="owner20@example.com", hashed_password="x", is_verified=True
    )
    other = models.User(
        email="other20@example.com", hashed_password="x", is_verified=True
    )
    post = models.Post(title="t", content="c", owner=owner)
    session.add_all([owner, other, post])
    session.commit()
    session.refresh(owner)
    session.refresh(other)
    session.refresh(post)

    service = _stubbed_service(session, monkeypatch, [])
    with pytest.raises(HTTPException) as exc:
        service.update_post(
            post_id=post.id,
            payload=post_schemas.PostCreate(
                title="new",
                content="change",
                published=True,
                hashtags=[],
            ),
            current_user=other,
            analyze_content_fn=None,
        )
    assert exc.value.status_code == 403


def test_poll_vote_duplicate_and_closed(session, monkeypatch):
    user = models.User(
        email="poll20@example.com", hashed_password="x", is_verified=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    service = _stubbed_service(session, monkeypatch, [])

    poll_post = service.create_poll_post(
        background_tasks=BackgroundTasks(),
        payload=post_schemas.PollCreate(
            title="poll",
            description="desc",
            options=["a", "b"],
            end_date=datetime.now(timezone.utc) + timedelta(days=1),
        ),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
    )
    options = session.query(models.PollOption).filter_by(post_id=poll_post.id).all()
    option_a, option_b = options[0], options[1]

    ok = service.vote_in_poll(
        post_id=poll_post.id, option_id=option_a.id, current_user=user
    )
    assert ok["message"] == "Vote recorded successfully"
    with pytest.raises(HTTPException):
        service.vote_in_poll(
            post_id=poll_post.id, option_id=option_a.id, current_user=user
        )

    # Switch vote to option B
    ok2 = service.vote_in_poll(
        post_id=poll_post.id, option_id=option_b.id, current_user=user
    )
    assert ok2["message"] == "Vote recorded successfully"

    # Expired poll rejects
    poll = session.query(models.Poll).filter_by(post_id=poll_post.id).first()
    poll.end_date = datetime.now(timezone.utc) - timedelta(days=1)
    session.commit()
    with pytest.raises(HTTPException):
        service.vote_in_poll(
            post_id=poll_post.id, option_id=option_b.id, current_user=user
        )


def _ns(**kwargs):
    from types import SimpleNamespace

    return SimpleNamespace(**kwargs)


def test_repost_updates_stats_and_notifications(session, monkeypatch):
    owner = models.User(
        email="orig20@example.com", hashed_password="x", is_verified=True
    )
    reposter = models.User(
        email="reposter20@example.com", hashed_password="x", is_verified=True
    )
    post = models.Post(
        title="orig", content="base", owner=owner, is_published=True, allow_reposts=True
    )
    session.add_all([owner, reposter, post])
    session.commit()
    session.refresh(post)

    stats = []
    notif = {}
    monkeypatch.setattr(
        post_service, "update_repost_statistics", lambda db, pid: stats.append(pid)
    )
    monkeypatch.setattr(
        post_service,
        "send_repost_notification",
        lambda db, orig_id, rep_id, new_id: notif.update(
            {"orig": orig_id, "rep": rep_id, "new": new_id}
        ),
    )
    service = PostService(session)
    monkeypatch.setattr(service, "_check_repost_permissions", lambda *a, **k: True)

    payload = _ns(
        content="reshare",
        community_id=None,
        allow_reposts=True,
        share_scope="public",
        visibility="all_members",
        custom_message=None,
        repost_settings=None,
    )
    created = service.repost_post(
        post_id=post.id, payload=payload, current_user=reposter
    )

    session.refresh(post)
    assert post.repost_count == 1
    assert stats == [post.id]
    assert (
        notif["orig"] == owner.id
        and notif["rep"] == reposter.id
        and notif["new"] == created.id
    )


def test_repost_community_scope_notifies_members(session, monkeypatch):
    owner = models.User(
        email="orig21@example.com", hashed_password="x", is_verified=True
    )
    reposter = models.User(
        email="reposter21@example.com", hashed_password="x", is_verified=True
    )
    community = models.Community(name="c1", owner=owner, is_active=True)
    session.add_all([owner, reposter, community])
    session.commit()
    session.refresh(reposter)
    session.refresh(community)
    member = models.CommunityMember(user_id=reposter.id, community=community)
    post = models.Post(
        title="orig",
        content="base",
        owner=owner,
        is_published=True,
        allow_reposts=True,
        community=community,
    )
    session.add_all([member, post])
    session.commit()
    session.refresh(post)

    monkeypatch.setattr(post_service, "update_repost_statistics", lambda *a, **k: None)
    monkeypatch.setattr(post_service, "send_repost_notification", lambda *a, **k: None)

    called = {"notify": False}

    def fake_notify(post_obj):
        called["notify"] = True

    service = PostService(session)
    monkeypatch.setattr(service, "_check_repost_permissions", lambda *a, **k: True)
    monkeypatch.setattr(service, "_notify_community_members", fake_notify)

    payload = _ns(
        content="reshare",
        community_id=community.id,
        allow_reposts=True,
        share_scope="community",
        visibility="members",
        custom_message="hi",
        repost_settings=None,
    )
    created = service.repost_post(
        post_id=post.id, payload=payload, current_user=reposter
    )
    assert created.community_id == community.id
    assert called["notify"] is True


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def test_get_post_applies_translation(session, monkeypatch):
    user = models.User(
        email="trans@example.com",
        hashed_password="x",
        is_verified=True,
        preferred_language="en",
    )
    post = models.Post(title="hola", content="mundo", owner=user, language="es")
    session.add_all([user, post])
    session.commit()
    session.refresh(post)

    service = PostService(session)
    calls = []

    async def translator(text, current_user, lang):
        calls.append((text, lang, current_user.id))
        return f"tr-{text}"

    result = asyncio_run(
        service.get_post(post_id=post.id, current_user=user, translator_fn=translator)
    )
    assert result.content == "tr-mundo"
    assert result.title == "tr-hola"
    assert len(calls) == 2
