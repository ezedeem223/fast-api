import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException

from app.services.comments.service import CommentService
from app.modules.posts.models import Post, Comment
from app.modules.users.models import User
from app.modules.notifications import manager as notifications_manager
from app.schemas import CommentCreate, CommentUpdate
from datetime import timedelta


def _user(session, email="u@example.com", verified=True):
    user = User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _post(session, owner):
    p = Post(title="t", content="c", owner_id=owner.id)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_create_comment_permissions_and_length(session, monkeypatch):
    user = _user(session)
    post = _post(session, user)
    service = CommentService(session)

    # not verified
    user.is_verified = False
    session.commit()
    with pytest.raises(HTTPException):
        await service.create_comment(
            schema=CommentCreate(content="hi", post_id=post.id),
            current_user=user,
            background_tasks=BackgroundTasks(),
        )

    # verified path
    user.is_verified = True
    session.commit()
    notifications_manager.broadcast = lambda *_, **__: None
    created = await service.create_comment(
        schema=CommentCreate(content="valid content", post_id=post.id),
        current_user=user,
        background_tasks=BackgroundTasks(),
    )
    assert created.id is not None
    assert created.owner_id == user.id


def test_delete_comment_auth_and_not_found(session):
    user = _user(session)
    other = _user(session, email="o@example.com")
    post = _post(session, user)
    comment = Comment(content="c", owner_id=user.id, post_id=post.id)
    session.add(comment)
    session.commit()
    session.refresh(comment)
    service = CommentService(session)

    with pytest.raises(HTTPException):
        service.delete_comment(comment_id=999, current_user=user)

    with pytest.raises(HTTPException):
        service.delete_comment(comment_id=comment.id, current_user=other)

    result = service.delete_comment(comment_id=comment.id, current_user=user)
    assert result["message"]
    session.refresh(comment)
    assert comment.is_deleted is True


def test_update_comment_window_and_content(session):
    user = _user(session)
    post = _post(session, user)
    comment = Comment(content="old", owner_id=user.id, post_id=post.id)
    session.add(comment)
    session.commit()
    session.refresh(comment)

    service = CommentService(session)
    updated = service.update_comment(
        comment_id=comment.id,
        payload=CommentUpdate(content="new"),
        current_user=user,
        edit_window=None,
    )
    assert updated.content == "new"

    # edit window expired
    comment.created_at = comment.created_at - timedelta(seconds=10)
    session.commit()
    with pytest.raises(HTTPException):
        service.update_comment(
            comment_id=comment.id,
            payload=CommentUpdate(content="late"),
            current_user=user,
            edit_window=timedelta(seconds=1),
        )
