import pytest

from app import models
from app.services import reporting
from app.services.comments.service import CommentService
from app.services.social.follow_service import FollowService
from app.services.users.service import UserService
from fastapi import BackgroundTasks, HTTPException


@pytest.mark.asyncio
async def test_comments_list_pagination_and_ordering(monkeypatch, session):
    # Stub translation to avoid external dependencies during listing.
    async def _stub_translate(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.services.comments.service.get_translated_content", _stub_translate
    )

    user = models.User(email="c1@example.com", hashed_password="x", is_verified=True)
    user.auto_translate = False
    session.add(user)
    session.commit()
    session.refresh(user)

    post = models.Post(owner_id=user.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    c1 = models.Comment(owner_id=user.id, post_id=post.id, content="c1", likes_count=1)
    c2 = models.Comment(owner_id=user.id, post_id=post.id, content="c2", likes_count=5)
    c3 = models.Comment(owner_id=user.id, post_id=post.id, content="c3", likes_count=3)
    session.add_all([c1, c2, c3])
    session.commit()

    svc = CommentService(session)
    comments = await svc.list_comments(
        post_id=post.id,
        current_user=user,
        sort_by="likes_count",
        sort_order="desc",
        skip=1,
        limit=1,
    )
    # With likes_count ordering desc, the middle item should be returned after skip=1.
    assert len(comments) == 1
    assert comments[0].likes_count == 3


def _make_user(session, **kwargs):
    email = kwargs.pop("email", f"u{session.query(models.User).count()}@ex.com")
    user = models.User(email=email, hashed_password="x", **kwargs)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_user_enforcement_actions(session, monkeypatch):
    svc = UserService(session)
    user = _make_user(session)

    # suspend
    out = svc.suspend_user(user.id, days=2)
    session.refresh(user)
    assert out["message"]
    assert user.is_suspended is True
    assert user.suspension_end_date is not None

    # activate clears suspension and verifies
    out = svc.activate_user(user.id)
    session.refresh(user)
    assert out["message"]
    assert user.is_suspended is False
    assert user.is_verified is True

    # lock account sets lock window
    out = svc.lock_account(user.id, minutes=15)
    session.refresh(user)
    assert out["message"]
    assert user.account_locked_until is not None

    # admin-only action denied for non-admin
    with pytest.raises(HTTPException) as exc:
        svc.perform_admin_action(user, action="dangerous")
    assert exc.value.status_code == 403

    # revoke tokens rolls back on failure
    user_token = "tok123"
    called = {"rollback": False}

    def boom():
        raise RuntimeError("db down")

    def mark_rollback():
        called["rollback"] = True

    monkeypatch.setattr(session, "commit", boom)
    monkeypatch.setattr(session, "rollback", mark_rollback)
    with pytest.raises(RuntimeError):
        svc.revoke_tokens(user, [user_token])
    assert called["rollback"] is True
    assert session.query(models.TokenBlacklist).count() == 0


def test_follow_permission_denied_for_suspended(session):
    suspended = _make_user(session, is_suspended=True)
    target = _make_user(session, email="target@example.com")

    svc = FollowService(session)
    with pytest.raises(HTTPException) as exc:
        svc.follow_user(
            background_tasks=BackgroundTasks(),
            current_user=suspended,
            target_user_id=target.id,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            notification_manager=type("N", (), {"broadcast": lambda self, msg: None})(),
            create_notification_fn=lambda *a, **k: None,
        )
    assert exc.value.status_code == 403


def test_reporting_missing_data_and_limits(session):
    reporter = _make_user(session)
    post = models.Post(owner_id=reporter.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    # missing data -> 400
    with pytest.raises(HTTPException) as exc:
        reporting.submit_report(
            session, reporter, reason="r", post_id=None, comment_id=None
        )
    assert exc.value.status_code == 400

    # first report OK
    reporting.submit_report(session, reporter, reason="valid", post_id=post.id)
    assert session.query(models.Report).count() == 1

    # duplicate rejected before hitting rate limit
    with pytest.raises(HTTPException) as exc:
        reporting.submit_report(session, reporter, reason="valid", post_id=post.id)
    assert exc.value.status_code == 409
