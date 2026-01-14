"""Additional coverage for reaction router branches."""

from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from app import models
from app.routers import reaction as reaction_router


def _direct_create_reaction(**kwargs):
    func = reaction_router.create_reaction
    if hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func(**kwargs)


def _make_user(session, email="r@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_post(session, owner_id):
    post = models.Post(owner_id=owner_id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def _make_comment(session, post_id, user_id):
    comment = models.Comment(post_id=post_id, owner_id=user_id, content="hi")
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


def test_create_reaction_missing_ids_returns_400(session):
    """Missing post_id/comment_id raises 400."""
    user = _make_user(session)
    reaction = SimpleNamespace(reaction_type="like")
    with pytest.raises(HTTPException) as exc:
        _direct_create_reaction(
            request=SimpleNamespace(),
            reaction=reaction,
            post_id=None,
            comment_id=None,
            db=session,
            current_user=user,
        )
    assert exc.value.status_code == 400
    assert (
        exc.value.detail == "Either post_id or comment_id must be provided"
    )


def test_create_reaction_both_ids_returns_400(session):
    """Providing both post_id and comment_id raises 400."""
    user = _make_user(session)
    reaction = SimpleNamespace(reaction_type="like", post_id=1)
    with pytest.raises(HTTPException) as exc:
        _direct_create_reaction(
            request=SimpleNamespace(),
            reaction=reaction,
            post_id=1,
            comment_id=2,
            db=session,
            current_user=user,
        )
    assert exc.value.status_code == 400
    assert (
        exc.value.detail
        == "Only one of post_id or comment_id should be provided"
    )


def test_create_reaction_post_not_found(session):
    """Nonexistent post triggers 404."""
    user = _make_user(session)
    reaction = SimpleNamespace(reaction_type="like", post_id=9999)
    with pytest.raises(HTTPException) as exc:
        _direct_create_reaction(
            request=SimpleNamespace(),
            reaction=reaction,
            post_id=None,
            comment_id=None,
            db=session,
            current_user=user,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Post not found"


def test_create_reaction_comment_not_found(session):
    """Nonexistent comment triggers 404."""
    user = _make_user(session)
    reaction = SimpleNamespace(reaction_type="like", post_id=None, comment_id=9999)
    with pytest.raises(HTTPException) as exc:
        _direct_create_reaction(
            request=SimpleNamespace(),
            reaction=reaction,
            post_id=None,
            comment_id=None,
            db=session,
            current_user=user,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Comment not found"


def test_create_reaction_existing_same_type_removes(session):
    """Same reaction removes existing row."""
    user = _make_user(session, email="same@example.com")
    post = _make_post(session, user.id)
    existing = models.Reaction(
        user_id=user.id, post_id=post.id, reaction_type="like"
    )
    session.add(existing)
    session.commit()

    reaction = SimpleNamespace(reaction_type="like", post_id=post.id)
    result = _direct_create_reaction(
        request=SimpleNamespace(),
        reaction=reaction,
        post_id=None,
        comment_id=None,
        db=session,
        current_user=user,
    )
    assert result["message"] == "Reaction removed"
    remaining = session.query(models.Reaction).filter_by(id=existing.id).first()
    assert remaining is None


def test_create_reaction_existing_diff_updates(session):
    """Different reaction updates existing row."""
    user = _make_user(session, email="diff@example.com")
    post = _make_post(session, user.id)
    existing = models.Reaction(
        user_id=user.id, post_id=post.id, reaction_type="like"
    )
    session.add(existing)
    session.commit()

    reaction = SimpleNamespace(reaction_type="love", post_id=post.id)
    result = _direct_create_reaction(
        request=SimpleNamespace(),
        reaction=reaction,
        post_id=None,
        comment_id=None,
        db=session,
        current_user=user,
    )
    assert result.reaction_type == "love"
    updated = session.query(models.Reaction).filter_by(id=existing.id).first()
    assert updated.reaction_type == "love"


def test_create_reaction_comment_updates_economy_exception(session, monkeypatch):
    """Comment reactions resolve post_id and swallow economy failures."""
    user = _make_user(session, email="comment@example.com")
    post = _make_post(session, user.id)
    comment = _make_comment(session, post.id, user.id)

    class DummyEconomy:
        def __init__(self, db):
            self.db = db

        def update_post_score(self, post_id):
            raise RuntimeError("boom")

    monkeypatch.setattr(reaction_router, "SocialEconomyService", DummyEconomy)
    reaction = SimpleNamespace(reaction_type="like", post_id=None, comment_id=comment.id)

    result = _direct_create_reaction(
        request=SimpleNamespace(),
        reaction=reaction,
        post_id=None,
        comment_id=None,
        db=session,
        current_user=user,
    )
    assert result.comment_id == comment.id
    assert result.post_id is None


def test_reaction_counts_for_post_and_comment(session):
    """Counts endpoints group reactions by type."""
    user = _make_user(session, email="counts@example.com")
    post = _make_post(session, user.id)
    comment = _make_comment(session, post.id, user.id)
    session.add_all(
        [
            models.Reaction(
                user_id=user.id, post_id=post.id, reaction_type="like"
            ),
            models.Reaction(
                user_id=user.id, post_id=post.id, reaction_type="love"
            ),
            models.Reaction(
                user_id=user.id,
                comment_id=comment.id,
                reaction_type="like",
            ),
        ]
    )
    session.commit()

    post_counts = reaction_router.get_post_reaction_counts(post.id, db=session)
    assert {c["reaction_type"] for c in post_counts} == {"like", "love"}

    comment_counts = reaction_router.get_comment_reaction_counts(comment.id, db=session)
    assert comment_counts[0]["reaction_type"] == "like"
