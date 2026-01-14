"""Test module for test auth security extended."""
import datetime

import pyotp
import pytest

from app import models
from app.modules.users.models import UserRole
from app.oauth2 import create_access_token
from app.routers.auth import MAX_LOGIN_ATTEMPTS
from fastapi import status


def _auth_headers(token: str) -> dict:
    """Helper for  auth headers."""
    return {"Authorization": f"Bearer {token}"}


def test_login_lockout_sets_account_locked(session, client, test_user):
    """When max failed attempts are reached, account_locked_until should be set."""
    user = session.get(models.User, test_user["id"])
    user.failed_login_attempts = MAX_LOGIN_ATTEMPTS - 1
    session.commit()

    res = client.post(
        "/login",
        data={"username": test_user["email"], "password": "wrong-password"},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    user = session.get(models.User, test_user["id"])
    assert user.account_locked_until is not None
    lock_time = user.account_locked_until
    if lock_time.tzinfo is None:
        lock_time = lock_time.replace(tzinfo=datetime.timezone.utc)
    assert lock_time > datetime.datetime.now(datetime.timezone.utc)


def test_login_requires_2fa_and_successful_otp(session, client, test_user):
    """Enabling 2FA should return sentinel token then allow OTP login."""
    secret = pyotp.random_base32()
    user = session.get(models.User, test_user["id"])
    user.is_2fa_enabled = True
    user.otp_secret = secret
    session.commit()

    res = client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["access_token"] == "2FA_REQUIRED"

    totp = pyotp.TOTP(secret)
    res_otp = client.post(
        f"/login/2fa?user_id={test_user['id']}", json={"otp": totp.now()}
    )
    assert res_otp.status_code == 200
    assert res_otp.json()["token_type"] == "bearer"


def test_login_2fa_invalid_otp(session, client, test_user):
    """Test case for test login 2fa invalid otp."""
    secret = pyotp.random_base32()
    user = session.get(models.User, test_user["id"])
    user.is_2fa_enabled = True
    user.otp_secret = secret
    session.commit()

    res = client.post(
        "/login/2fa",
        params={"user_id": test_user["id"]},
        json={"otp": "000000"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid OTP code"


def test_admin_stats_requires_admin_role(session, client, test_user):
    """Non-admin users should be blocked from admin-only helpers."""
    user = session.get(models.User, test_user["id"])
    user.is_admin = False
    session.commit()
    token = create_access_token({"user_id": test_user["id"]})
    with pytest.raises(Exception):
        # Should raise HTTPException due to missing admin role
        from app.oauth2 import get_current_admin

        get_current_admin(token=token, db=session)


def test_admin_stats_allows_admin(session, client):
    """Admin role should pass the admin guard successfully."""
    admin_user = models.User(
        email="admin@example.com",
        hashed_password="hashed",
        role=UserRole.ADMIN,
        is_verified=True,
    )
    admin_user.is_admin = True
    session.add(admin_user)
    session.commit()
    token = create_access_token({"user_id": admin_user.id})

    from app.oauth2 import get_current_admin

    current_admin = get_current_admin(token=token, db=session)
    assert current_admin.id == admin_user.id
    assert getattr(current_admin, "is_admin", False)


def test_moderator_reports_requires_membership(session, client):
    """Moderator without community membership should be rejected."""
    mod_user = models.User(
        email="mod@example.com",
        hashed_password="hashed",
        role=UserRole.MODERATOR,
        is_verified=True,
    )
    # set ad-hoc flag expected by router
    mod_user.is_moderator = True
    session.add(mod_user)
    session.commit()
    token = create_access_token({"user_id": mod_user.id})

    res = client.get("/moderator/community/1/reports", headers=_auth_headers(token))
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["detail"] == "Not authorized for this community"
