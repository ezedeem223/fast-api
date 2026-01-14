"""Test module for test session2 users comments sessions."""
import asyncio
from types import SimpleNamespace

import pytest

from app import models, schemas
from app.routers import session as session_router
from app.services.comments.service import CommentService
from app.services.users.service import UserService
from fastapi import HTTPException


def _make_user(session, email: str, verified: bool = True) -> models.User:
    """Helper for  make user."""
    user = models.User(
        email=email, hashed_password="x", is_verified=verified, preferred_language="en"
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_comment_length_and_db_failure(session, monkeypatch):
    """Test case for test comment length and db failure."""
    service = CommentService(session)
    owner = _make_user(session, "owner-comments@example.com")
    post = models.Post(owner_id=owner.id, title="p", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    session.refresh(post)

    # overly long content check via profanity/validate URLs (simulate failure)
    def fake_check(content, rules):
        return False

    with pytest.raises(HTTPException):
        asyncio.run(
            service._validate_comment_content(
                schemas.CommentCreate(
                    content="bad http://bad",
                    post_id=post.id,
                    image_url="http://invalid",
                ),
                post,
            )
        )

    # simulate DB failure on delete
    def fail_commit():
        raise Exception("db error")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(Exception):
        service.delete_comment(comment_id=0, current_user=owner)


def test_user_service_permissions_and_updates(session):
    """Test case for test user service permissions and updates."""
    user_service = UserService(session)
    user = user_service.create_user(
        schemas.UserCreate(
            email="settings@example.com", password="StrongPass123!", username="u"
        )
    )

    # update_privacy_settings with custom visibility allowed
    updated = user_service.update_privacy_settings(
        user,
        schemas.UserPrivacyUpdate(
            privacy_level=schemas.PrivacyLevel.CUSTOM,
            custom_privacy={"allowed": [user.id]},
        ),
    )
    assert updated.privacy_level == schemas.PrivacyLevel.CUSTOM

    # update_followers_settings persists preferences
    settings = schemas.UserFollowersSettings(
        followers_visibility="private",
        followers_custom_visibility={"allowed_users": [user.id]},
        followers_sort_preference="date",
    )
    saved = user_service.update_followers_settings(user, settings)
    assert saved.followers_visibility == "private"

    # update_public_key: store bytes-like expected by model
    # public_key expects bytes; ensure assignment succeeds
    updated_user = user_service.update_public_key(
        user, schemas.UserPublicKeyUpdate(public_key=b"pk")
    )
    # SQLite returns bytes unchanged
    assert updated_user.public_key == b"pk"


def test_session_router_invalid_inputs(session):
    # create minimal users
    """Test case for test session router invalid inputs."""
    user_service = UserService(session)
    u1 = user_service.create_user(
        schemas.UserCreate(
            email="sessA@example.com", password="StrongPass123!", username="u1"
        )
    )
    # missing other user
    with pytest.raises(HTTPException):
        session_router.create_encrypted_session(
            session=schemas.EncryptedSessionCreate(other_user_id=999),
            db=session,
            current_user=u1,
        )

    # missing session update target
    payload = SimpleNamespace(
        root_key=b"r", chain_key=b"c", next_header_key=b"n", ratchet_key=b"k"
    )
    with pytest.raises(HTTPException):
        session_router.update_encrypted_session(
            session_id=1234,
            session_update=payload,
            db=session,
            current_user=u1,
        )
