import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest
from jose import jwt

from app import models, oauth2
from app.core.config import settings
from app.modules.community import Community, CommunityMember, CommunityRole
from app.modules.users.models import UserRole
from app.modules.utils.security import hash as hash_password
from app.oauth2 import create_access_token
from app.routers import admin_dashboard
from app.routers import auth as auth_router
from fastapi import HTTPException


def _make_user(
    session, email="auth@example.com", password="pass", role=UserRole.USER, **kwargs
):
    user = models.User(
        email=email,
        hashed_password=hash_password(password),
        is_verified=True,
        role=role,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_login_success_invalid_and_lockout_flow(client, session):
    user = _make_user(session, email="lock@example.com", password="secret")

    # successful login returns token
    ok_resp = client.post("/login", data={"username": user.email, "password": "secret"})
    assert ok_resp.status_code == 200
    assert ok_resp.json()["access_token"]

    # trigger lockout with repeated wrong passwords
    for _ in range(auth_router.MAX_LOGIN_ATTEMPTS):
        resp = client.post("/login", data={"username": user.email, "password": "bad"})
        assert resp.status_code == 403
    user = session.get(models.User, user.id)
    assert user.account_locked_until is not None
    assert user.failed_login_attempts >= auth_router.MAX_LOGIN_ATTEMPTS


def test_login_2fa_success_and_failure(client, session):
    secret = pyotp.random_base32()
    user = _make_user(
        session,
        email="2fa@example.com",
        password="otp-pass",
        is_2fa_enabled=True,
        otp_secret=secret,
    )

    resp = client.post("/login", data={"username": user.email, "password": "otp-pass"})
    data = resp.json()
    assert data["access_token"] == "2FA_REQUIRED"

    # invalid OTP
    bad_otp = "000000"
    bad = client.post(
        "/login/2fa",
        params={"user_id": user.id},
        json={"otp": bad_otp},
    )
    assert bad.status_code == 400

    # valid OTP
    good_otp = pyotp.TOTP(secret).now()
    ok = client.post(
        "/login/2fa",
        params={"user_id": user.id},
        json={"otp": good_otp},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_refresh_and_logout_blacklists_token(client, session):
    user = _make_user(session, email="refresh@example.com", password="pw")
    # craft refresh token
    original_refresh_key = settings.refresh_secret_key
    try:
        settings.refresh_secret_key = settings.rsa_private_key
        refresh_token = jwt.encode(
            {"sub": str(user.id)},
            settings.refresh_secret_key,
            algorithm=settings.algorithm,
        )
        settings.refresh_secret_key = settings.rsa_public_key
        refreshed = client.post(
            "/refresh-token", params={"refresh_token": refresh_token}
        )
        assert refreshed.status_code == 200
        assert "access_token" in refreshed.json()
    finally:
        settings.refresh_secret_key = original_refresh_key

    # login to create session then logout
    login_resp = client.post("/login", data={"username": user.email, "password": "pw"})
    token = login_resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    original_verify = oauth2.verify_access_token

    def _fake_verify(tok, exc):
        data = jwt.decode(tok, settings.rsa_public_key, algorithms=[settings.algorithm])
        return SimpleNamespace(
            id=data.get("user_id"), session_id=data.get("session_id")
        )

    oauth2.verify_access_token = _fake_verify
    out = client.post("/logout")
    oauth2.verify_access_token = original_verify
    assert out.status_code == 200
    # session removed and token blacklisted
    assert (
        session.query(models.UserSession)
        .filter(models.UserSession.user_id == user.id)
        .count()
        == 0
    )
    assert (
        session.query(models.TokenBlacklist)
        .filter(models.TokenBlacklist.token == token)
        .count()
        == 1
    )


def test_oauth2_token_creation_and_expiry_handling():
    token = create_access_token({"user_id": 5, "session_id": "sess-1"})
    cred_exc = HTTPException(status_code=401, detail="Invalid Credentials")
    data = oauth2.verify_access_token(token, cred_exc)
    assert data.id == 5

    expired = jwt.encode(
        {"user_id": 5, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.rsa_private_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(HTTPException):
        oauth2.verify_access_token(expired, cred_exc)

    # missing session_id should be rejected by get_current_session
    with pytest.raises(HTTPException):
        oauth2.get_current_session(token=create_access_token({"user_id": 9}))


def test_admin_and_moderator_authorization(client, session):
    admin_user = _make_user(
        session, email="admin@example.com", password="x", role=UserRole.ADMIN
    )
    normal_user = _make_user(
        session, email="user@example.com", password="x", role=UserRole.USER
    )

    # admin access allowed via dependency function
    assert (
        asyncio.run(admin_dashboard.get_current_admin(current_user=admin_user))
        == admin_user
    )
    with pytest.raises(HTTPException):
        asyncio.run(admin_dashboard.get_current_admin(current_user=normal_user))

    # moderator routes: allow authorized member, deny non-member
    mod_user = _make_user(
        session, email="mod@example.com", password="x", role=UserRole.MODERATOR
    )
    community = Community(name="C", description="d", owner_id=mod_user.id)
    session.add(community)
    session.commit()
    session.refresh(community)
    member = CommunityMember(
        community_id=community.id,
        user_id=mod_user.id,
        role=CommunityRole.MODERATOR,
    )
    session.add(member)
    session.commit()

    client.app.dependency_overrides[oauth2.get_current_user] = lambda: mod_user
    members_ok = client.get(f"/moderator/community/{community.id}/members")
    assert members_ok.status_code == 200

    client.app.dependency_overrides[oauth2.get_current_user] = lambda: normal_user
    members_forbidden = client.get(f"/moderator/community/{community.id}/members")
    assert members_forbidden.status_code == 403

    client.app.dependency_overrides.pop(oauth2.get_current_user, None)
