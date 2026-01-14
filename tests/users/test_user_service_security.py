"""Test module for test user service session23."""
import pytest

from app import models, schemas
from app.services.users.service import UserService
from fastapi import HTTPException


def _user(session, email="u@example.com", verified=True, password="secret"):
    """Helper for  user."""
    user = models.User(
        email=email,
        hashed_password=password,
        is_verified=verified,
        privacy_level=schemas.PrivacyLevel.PUBLIC,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_create_user_duplicate_email(session):
    """Test case for test create user duplicate email."""
    service = UserService(session)
    payload = schemas.UserCreate(email="dup@example.com", password="StrongPass123!")
    service.create_user(payload)

    with pytest.raises(HTTPException) as exc:
        service.create_user(payload)
    assert exc.value.status_code == 400
    assert "Email already registered" in exc.value.detail


def test_create_user_invalid_public_key_type(session):
    """Test case for test create user invalid public key type."""
    service = UserService(session)
    with pytest.raises(HTTPException) as exc:
        service._coerce_public_key(object())
    assert exc.value.status_code == 400
    assert (
        exc.value.detail == "Invalid public key type; expected bytes or str"
    )


def test_update_privacy_custom_requires_map(session):
    """Test case for test update privacy custom requires map."""
    service = UserService(session)
    user = _user(session)
    update = schemas.UserPrivacyUpdate(
        privacy_level=schemas.PrivacyLevel.CUSTOM, custom_privacy=None
    )

    with pytest.raises(HTTPException) as exc:
        service.update_privacy_settings(user, update)
    assert exc.value.status_code == 400
    assert (
        exc.value.detail
        == "Custom privacy settings required for CUSTOM privacy level"
    )


def test_update_privacy_custom_applies(session):
    """Test case for test update privacy custom applies."""
    service = UserService(session)
    user = _user(session)
    prefs = {"allowed_users": [user.id]}
    update = schemas.UserPrivacyUpdate(
        privacy_level=schemas.PrivacyLevel.CUSTOM, custom_privacy=prefs
    )

    updated = service.update_privacy_settings(user, update)
    assert updated.privacy_level == schemas.PrivacyLevel.CUSTOM
    assert updated.custom_privacy == prefs


def test_change_password_validates_and_updates(monkeypatch, session):
    """Test case for test change password validates and updates."""
    service = UserService(session)
    user = _user(session, password="oldhash")

    monkeypatch.setattr(
        "app.services.users.service.verify", lambda current, hashed: False
    )
    with pytest.raises(HTTPException) as exc:
        service.change_password(
            user,
            schemas.PasswordChange(
                current_password="bad", new_password="NewPass123!"
            ),
        )
    assert exc.value.status_code == 400

    monkeypatch.setattr(
        "app.services.users.service.verify", lambda current, hashed: True
    )
    monkeypatch.setattr(
        "app.services.users.service.hash_password", lambda pw: f"hashed-{pw}"
    )
    result = service.change_password(
        user,
        schemas.PasswordChange(
            current_password="old", new_password="NewPass123!"
        ),
    )
    assert result["message"] == "Password changed successfully"
    assert user.hashed_password == "hashed-NewPass123!"


def test_enable_and_verify_2fa_flow(monkeypatch, session):
    """Test case for test enable and verify 2fa flow."""
    service = UserService(session)
    user = _user(session)

    secret_resp = service.enable_2fa(user)
    assert "otp_secret" in secret_resp
    assert user.is_2fa_enabled is False

    class DummyTotp:
        def __init__(self, secret):
            self.secret = secret

        def verify(self, otp):
            return otp == "123456"

    monkeypatch.setattr("app.services.users.service.pyotp.TOTP", DummyTotp)

    with pytest.raises(HTTPException):
        service.verify_2fa(user, "000000")

    resp = service.verify_2fa(user, "123456")
    assert resp["message"] == "2FA verified successfully"
    assert user.is_2fa_enabled is True
