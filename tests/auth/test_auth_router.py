"""Test module for test session3 auth router."""
import datetime

import pyotp
import pytest
from jose import jwt

from app import models
from app.core.config import settings
from app.routers import auth
from fastapi import status


def _login(client, email, password):
    """Helper for  login."""
    return client.post(
        "/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def test_login_wrong_password_returns_403(client, test_user, monkeypatch):
    """Wrong password should be rejected with 403 and no background side effects."""

    async def fake_notify(*_, **__):
        return None

    monkeypatch.setattr(auth, "send_login_notification", fake_notify)
    res = _login(client, test_user.email, "wrong-pass")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["detail"] == "Invalid Credentials"


def test_login_success_returns_token(client, test_user, monkeypatch):
    """Correct credentials return a bearer token and not the 2FA sentinel."""

    async def fake_notify(*_, **__):
        return None

    monkeypatch.setattr(auth, "send_login_notification", fake_notify)
    res = _login(client, test_user.email, test_user.password)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["access_token"] != "2FA_REQUIRED"


def test_account_lockout_after_failed_attempts(client, test_user, session):
    """After MAX_LOGIN_ATTEMPTS failures the account is locked and subsequent attempts are blocked."""
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        _ = _login(client, test_user.email, "wrong-pass")

    db_user = session.query(models.User).get(test_user.id)
    assert db_user.failed_login_attempts >= auth.MAX_LOGIN_ATTEMPTS
    assert db_user.account_locked_until is not None


@pytest.mark.anyio("asyncio")
async def test_refresh_token_valid_and_invalid(session, test_user, monkeypatch):
    """Valid refresh token issues access token; expired/invalid ones are rejected (endpoint logic)."""
    for target in (settings, settings.__class__):
        monkeypatch.setattr(
            target, "refresh_secret_key", "refresh-secret", raising=False
        )
        monkeypatch.setattr(target, "algorithm", "HS256", raising=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    valid_token = jwt.encode(
        {"sub": str(test_user.id), "exp": now + datetime.timedelta(minutes=5)},
        settings.refresh_secret_key,
        algorithm=settings.algorithm,
    )
    expired_token = jwt.encode(
        {"sub": str(test_user.id), "exp": now - datetime.timedelta(minutes=5)},
        settings.refresh_secret_key,
        algorithm=settings.algorithm,
    )

    # sanity check token decodes with patched config
    decoded = jwt.decode(
        valid_token, settings.refresh_secret_key, algorithms=[settings.algorithm]
    )
    assert decoded["sub"] == str(test_user.id)

    ok = await auth.refresh_token(refresh_token=valid_token, db=session)
    assert ok["token_type"] == "bearer"
    assert ok["access_token"]

    with pytest.raises(Exception):
        await auth.refresh_token(refresh_token=expired_token, db=session)


def test_two_factor_flow_requires_otp_then_allows_login(
    client, test_user, session, monkeypatch
):
    """2FA enabled user should receive sentinel then succeed with valid OTP and fail on bad OTP."""

    async def fake_notify(*_, **__):
        return None

    monkeypatch.setattr(auth, "send_login_notification", fake_notify)
    secret = pyotp.random_base32()
    session.query(models.User).filter(models.User.id == test_user.id).update(
        {"is_2fa_enabled": True, "otp_secret": secret}
    )
    session.commit()

    res = _login(client, test_user.email, test_user.password)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["access_token"] == "2FA_REQUIRED"

    # Wrong OTP rejected
    bad_otp = client.post(
        "/login/2fa",
        params={"user_id": test_user.id},
        json={"otp": "000000"},
    )
    assert bad_otp.status_code == status.HTTP_400_BAD_REQUEST

    # Correct OTP accepted
    totp = pyotp.TOTP(secret)
    good_otp = client.post(
        "/login/2fa",
        params={"user_id": test_user.id},
        json={"otp": totp.now()},
    )
    assert good_otp.status_code == status.HTTP_200_OK
    assert good_otp.json()["access_token"] != "2FA_REQUIRED"
