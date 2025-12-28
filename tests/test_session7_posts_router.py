from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import models, schemas
from app.core.cache.redis_cache import cache_manager
from app.oauth2 import create_access_token
from app.routers.post import share_on_twitter
from app.services.posts.post_service import PostService
from tests.conftest import TestingSessionLocal


def _auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def test_create_post_invalidates_cache(monkeypatch, authorized_client):
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(cache_manager, "invalidate", invalidate_mock)

    resp = authorized_client.post(
        "/posts/",
        json={"title": "hello", "content": "world"},
    )
    assert resp.status_code == 201
    calls = [c.args[0] for c in invalidate_mock.await_args_list]
    assert "posts:list:*" in calls


def test_update_post_invalidates_cache(monkeypatch, authorized_client):
    create = authorized_client.post(
        "/posts/", json={"title": "t1", "content": "c1"}
    )
    post_id = create.json()["id"]
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(cache_manager, "invalidate", invalidate_mock)

    resp = authorized_client.put(
        f"/posts/{post_id}", json={"title": "t2", "content": "c2"}
    )
    assert resp.status_code == 200
    call_args = [c.args[0] for c in invalidate_mock.await_args_list]
    assert "posts:list:*" in call_args
    assert f"post:{post_id}" in call_args


def test_delete_post_invalidates_cache(monkeypatch, authorized_client):
    created = authorized_client.post(
        "/posts/", json={"title": "del", "content": "c"}
    ).json()
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(cache_manager, "invalidate", invalidate_mock)

    resp = authorized_client.delete(f"/posts/{created['id']}")
    assert resp.status_code == 204
    call_args = [c.args[0] for c in invalidate_mock.await_args_list]
    assert "posts:list:*" in call_args
    assert f"post:{created['id']}" in call_args


def _make_user(session, email="poll@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_poll_option_limit_enforced(session):
    service = PostService(session)
    user = _make_user(session, "limit@example.com")
    with pytest.raises(HTTPException) as exc:
        service.create_poll_post(
            background_tasks=None,
            payload=schemas.PollCreate(
                title="poll",
                description="d",
                options=[str(i) for i in range(12)],
                end_date=None,
            ),
            current_user=user,
            queue_email_fn=lambda *a, **k: None,
        )
    assert "option" in str(exc.value).lower()


def test_poll_vote_same_option_rejected(session):
    service = PostService(session)
    user = _make_user(session, "samevote@example.com")
    poll = service.create_poll_post(
        background_tasks=None,
        payload=schemas.PollCreate(
            title="poll", description="d", options=["a", "b"], end_date=None
        ),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
    )
    options = (
        session.query(models.PollOption)
        .filter(models.PollOption.post_id == poll.id)
        .all()
    )
    option_id = options[0].id
    service.vote_in_poll(post_id=poll.id, option_id=option_id, current_user=user)
    with pytest.raises(HTTPException):
        service.vote_in_poll(post_id=poll.id, option_id=option_id, current_user=user)


def test_closed_poll_rejects_vote(session):
    service = PostService(session)
    user = _make_user(session, "closed@example.com")
    poll = service.create_poll_post(
        background_tasks=None,
        payload=schemas.PollCreate(
            title="poll2",
            description="d2",
            options=["x", "y"],
            end_date=datetime.now() - timedelta(days=1),
        ),
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
    )
    option_id = (
        session.query(models.PollOption)
        .filter(models.PollOption.post_id == poll.id)
        .first()
        .id
    )
    with pytest.raises(HTTPException):
        service.vote_in_poll(post_id=poll.id, option_id=option_id, current_user=user)


def test_share_on_twitter_skips_without_credentials(monkeypatch):
    called = False

    def _fail_request(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Should not call requests when token is placeholder")

    monkeypatch.setattr("app.routers.post.requests.post", _fail_request)
    share_on_twitter("hello world")
    assert called is False


def test_export_post_as_pdf_stream(monkeypatch, test_user, client):
    with TestingSessionLocal() as db:
        post = models.Post(
            owner_id=test_user["id"], title="Pdf", content="Body", is_safe_content=True
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id

    monkeypatch.setattr(
        "app.services.posts.post_service._create_pdf",
        lambda post_obj: BytesIO(b"pdfbytes"),
    )

    headers = _auth_headers(test_user["id"])
    resp = client.get(f"/posts/{post_id}/export-pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"pdfbytes"
