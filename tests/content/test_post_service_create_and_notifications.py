"""Test module for test post service session21."""
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import models
from app.modules.posts import schemas as post_schemas
from app.services.posts import post_service
from app.services.posts.post_service import PostService, _create_pdf
from fastapi import BackgroundTasks, HTTPException


def _user(session, email="u@example.com", verified=True):
    """Helper for  user."""
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    setattr(user, "username", email.split("@")[0])
    return user


def _post_payload(**kwargs):
    """Helper for  post payload."""
    payload = {
        "title": "Hello",
        "content": "World",
        "hashtags": [],
        "category_id": None,
        "community_id": None,
        "is_help_request": False,
        "scheduled_time": None,
        "copyright_type": "public_domain",
        "custom_copyright": None,
        "is_encrypted": False,
        "encryption_key_id": None,
        "is_living_testimony": False,
        "related_to_post_id": None,
        "relation_type": None,
    }
    payload.update(kwargs)
    return post_schemas.PostCreate(**payload)


class DummyBackgroundTasks(BackgroundTasks):
    """Test class for DummyBackgroundTasks."""
    def __init__(self):
        super().__init__()
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))
        return super().add_task(func, *args, **kwargs)


def test_create_pdf_success(monkeypatch):
    """Test case for test create pdf success."""
    called = {}

    class DummyPisaDoc:
        def __init__(self, *args, **kwargs):
            self.err = False
            called["args"] = args

    class DummyPisa:
        def pisaDocument(self, *args, **kwargs):
            return DummyPisaDoc(*args, **kwargs)

    class DummyModule:
        def __init__(self):
            self.pisa = DummyPisa()

    monkeypatch.setitem(sys.modules, "xhtml2pdf", DummyModule())
    post = SimpleNamespace(
        title="T",
        content="C",
        created_at=datetime(2024, 1, 1),
        owner=SimpleNamespace(email="e@example.com", username="user1"),
    )
    pdf = _create_pdf(post)
    assert isinstance(pdf, BytesIO)
    assert called["args"]


def test_create_pdf_failure(monkeypatch):
    """Test case for test create pdf failure."""
    class DummyPisaDoc:
        def __init__(self, *args, **kwargs):
            self.err = True

    class DummyPisa:
        def pisaDocument(self, *args, **kwargs):
            return DummyPisaDoc()

    class DummyModule:
        def __init__(self):
            self.pisa = DummyPisa()

    monkeypatch.setitem(sys.modules, "xhtml2pdf", DummyModule())
    post = SimpleNamespace(
        title="T",
        content="C",
        created_at=datetime(2024, 1, 1),
        owner=SimpleNamespace(email="e@example.com"),
    )
    assert _create_pdf(post) is None


def test_create_post_mentions_and_notifications(monkeypatch, session):
    """Test case for test create post mentions and notifications."""
    # Arrange: build a post with mentions and stub notification hooks.
    service = PostService(session)
    user = _user(session)
    mentioned = _user(session, "m@example.com")
    payload = _post_payload(content=f"Hi @{mentioned.email}")
    bg = DummyBackgroundTasks()

    queue_calls = []
    schedule_calls = []
    broadcast_calls = []
    share_calls = []
    mention_calls = []

    def queue_email(tasks, **kwargs):
        queue_calls.append(kwargs)

    def schedule_email(tasks, **kwargs):
        schedule_calls.append(kwargs)

    def broadcast(msg):
        broadcast_calls.append(msg)

    def share_twitter(text):
        share_calls.append(("tw", text))

    def share_facebook(text):
        share_calls.append(("fb", text))

    async def mention(to, username, post_id):
        mention_calls.append((to, username, post_id))

    monkeypatch.setattr(
        post_service, "process_mentions", lambda content, db: [mentioned]
    )

    # Act: create the post and capture side effects.
    post_out = service.create_post(
        background_tasks=bg,
        payload=payload,
        current_user=user,
        queue_email_fn=queue_email,
        schedule_email_fn=schedule_email,
        broadcast_fn=broadcast,
        share_on_twitter_fn=share_twitter,
        share_on_facebook_fn=share_facebook,
        mention_notifier_fn=mention,
        analyze_content_fn=lambda text: {
            "sentiment": {"sentiment": "pos", "score": 0.7},
            "suggestion": "ok",
        },
    )

    # Assert: notifications and mention handlers are invoked.
    assert post_out.title == "Hello"
    assert queue_calls and schedule_calls
    assert broadcast_calls == ["New post created: Hello"]
    assert any("tw" in call for call in share_calls)
    assert post_out.mentioned_users
    assert any(task[0] == mention for task in bg.tasks)


def test_create_post_offensive_block(monkeypatch, session):
    """Test case for test create post offensive block."""
    service = PostService(session)
    user = _user(session)
    payload = _post_payload(content="bad content")

    monkeypatch.setattr(
        post_service, "check_content", lambda db, text: ([], ["banned"])
    )

    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=DummyBackgroundTasks(),
            payload=payload,
            current_user=user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda *a, **k: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
        )
    assert exc.value.status_code == 400
    assert "Content contains banned words" in exc.value.detail


def test_create_post_scheduled_enqueues(monkeypatch, session):
    """Test case for test create post scheduled enqueues."""
    service = PostService(session)
    user = _user(session)
    payload = _post_payload(
        content="scheduled",
        scheduled_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    bg = DummyBackgroundTasks()

    scheduled = []

    def fake_schedule_post_publication(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr(
        post_service,
        "schedule_post_publication",
        SimpleNamespace(apply_async=fake_schedule_post_publication),
    )

    service.create_post(
        background_tasks=bg,
        payload=payload,
        current_user=user,
        queue_email_fn=lambda *a, **k: None,
        schedule_email_fn=lambda *a, **k: None,
        broadcast_fn=lambda *a, **k: None,
        share_on_twitter_fn=lambda *a, **k: None,
        share_on_facebook_fn=lambda *a, **k: None,
        mention_notifier_fn=lambda *a, **k: None,
    )

    assert scheduled, "Expected scheduled publication to be enqueued"


def test_create_post_blocks_unverified(session):
    """Test case for test create post blocks unverified."""
    service = PostService(session)
    user = _user(session, verified=False)
    payload = _post_payload(content="hi")

    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=DummyBackgroundTasks(),
            payload=payload,
            current_user=user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda *a, **k: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "User is not verified."
