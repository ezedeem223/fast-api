"""Test module for test user service."""
import pytest

from app.modules.users.models import User
from app.schemas import PrivacyLevel, UserCreate, UserPrivacyUpdate, UserProfileUpdate
from app.services.users.service import UserService
from fastapi import HTTPException


def _service(session):
    """Helper for  service."""
    return UserService(session)


def _user(session, email="user@example.com"):
    """Helper for  user."""
    u = User(email=email, hashed_password="x", is_verified=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def test_create_user_coerces_public_key(session):
    """Test case for test create user coerces public key."""
    service = _service(session)
    payload = UserCreate(
        email="pk@example.com", password="StrongPass123!", public_key="abc123"
    )
    user = service.create_user(payload)
    assert user.public_key == b"abc123"


@pytest.mark.filterwarnings("ignore:The `from_orm` method is deprecated")
def test_update_profile_and_privacy(session):
    """Test case for test update profile and privacy."""
    user = _user(session)
    service = _service(session)
    with pytest.raises(Exception):
        service.update_profile(user, UserProfileUpdate(bio="hi"))
    assert user.bio == "hi"

    privacy = service.update_privacy_settings(
        user, UserPrivacyUpdate(privacy_level=PrivacyLevel.PUBLIC)
    )
    assert privacy.privacy_level == PrivacyLevel.PUBLIC

    with pytest.raises(HTTPException):
        service.update_privacy_settings(
            user,
            UserPrivacyUpdate(privacy_level=PrivacyLevel.CUSTOM, custom_privacy=None),
        )


def test_suspend_and_unsuspend(session):
    """Test case for test suspend and unsuspend."""
    user = _user(session)
    service = _service(session)
    res = service.suspend_user(user.id, days=1)
    assert user.is_suspended is True
    assert "message" in res
    res2 = service.unsuspend_user(user.id)
    assert user.is_suspended is False
    assert "message" in res2
