import pytest
from fastapi import HTTPException

from app.services.users.service import UserService
from app.modules.users.models import User
from app.schemas import (
    UserCreate,
    UserProfileUpdate,
    UserPrivacyUpdate,
    PrivacyLevel,
)


def _service(session):
    return UserService(session)


def _user(session, email="user@example.com"):
    u = User(email=email, hashed_password="x", is_verified=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def test_create_user_duplicate(session):
    service = _service(session)
    payload = UserCreate(email="dup@example.com", password="pw")
    service.create_user(payload)
    with pytest.raises(HTTPException):
        service.create_user(payload)


@pytest.mark.filterwarnings("ignore:The `from_orm` method is deprecated")
def test_update_profile_and_privacy(session):
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
    user = _user(session)
    service = _service(session)
    res = service.suspend_user(user.id, days=1)
    assert user.is_suspended is True
    assert "message" in res
    res2 = service.unsuspend_user(user.id)
    assert user.is_suspended is False
    assert "message" in res2
