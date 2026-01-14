"""Additional coverage for 2FA router error branches."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import p2fa as p2fa_router


class FakeDB:
    """Minimal DB stub for 2FA tests."""

    def __init__(self, fail_commit=False):
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_verify_totp_handles_exception(monkeypatch):
    """verify_totp returns False when pyotp fails."""

    class BoomTOTP:
        def __init__(self, _secret):
            raise RuntimeError("boom")

    monkeypatch.setattr(p2fa_router.pyotp, "TOTP", BoomTOTP)
    assert p2fa_router.TwoFactorAuth.verify_totp("secret", "123") is False


@pytest.mark.asyncio
async def test_enable_2fa_already_enabled():
    """Enable 2FA rejects when already enabled."""
    user = SimpleNamespace(is_2fa_enabled=True, otp_secret=None, email="u@example.com")
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.enable_2fa(current_user=user, db=db)
    assert exc.value.status_code == 400
    assert (
        exc.value.detail == "Two-factor authentication is already enabled."
    )


@pytest.mark.asyncio
async def test_enable_2fa_handles_exception(monkeypatch):
    """Enable 2FA rolls back on unexpected errors."""
    user = SimpleNamespace(is_2fa_enabled=False, otp_secret=None, email="u@example.com")
    db = FakeDB()

    monkeypatch.setattr(p2fa_router.TwoFactorAuth, "generate_secret", lambda: "sec")
    monkeypatch.setattr(
        p2fa_router.TwoFactorAuth,
        "generate_provisioning_uri",
        lambda *_: "uri",
    )

    def boom(_uri):
        raise RuntimeError("qr fail")

    monkeypatch.setattr(p2fa_router, "generate_qr_code", boom)

    with pytest.raises(HTTPException) as exc:
        await p2fa_router.enable_2fa(current_user=user, db=db)
    assert exc.value.status_code == 500
    assert exc.value.detail == "Error enabling two-factor authentication"
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_disable_2fa_not_enabled():
    """Disable 2FA rejects when not enabled."""
    user = SimpleNamespace(is_2fa_enabled=False, otp_secret=None)
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.disable_2fa(current_user=user, db=db)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Two-factor authentication is not enabled."


@pytest.mark.asyncio
async def test_disable_2fa_handles_commit_error():
    """Disable 2FA rolls back on commit failure."""
    user = SimpleNamespace(is_2fa_enabled=True, otp_secret="secret")
    db = FakeDB(fail_commit=True)
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.disable_2fa(current_user=user, db=db)
    assert exc.value.status_code == 500
    assert exc.value.detail == "Error disabling two-factor authentication"
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_verify_2fa_not_enabled():
    """Verify 2FA rejects when not enabled."""
    user = SimpleNamespace(is_2fa_enabled=False, otp_secret=None)
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.verify_2fa(
            otp=SimpleNamespace(otp="123"), current_user=user, db=db
        )
    assert exc.value.status_code == 400
    assert (
        exc.value.detail
        == "Two-factor authentication is not enabled for this user."
    )


@pytest.mark.asyncio
async def test_verify_2fa_invalid_otp(monkeypatch):
    """Verify 2FA returns 400 for invalid OTP."""
    user = SimpleNamespace(is_2fa_enabled=True, otp_secret="secret")
    db = FakeDB()
    monkeypatch.setattr(p2fa_router.TwoFactorAuth, "verify_totp", lambda *_: False)
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.verify_2fa(
            otp=SimpleNamespace(otp="bad"), current_user=user, db=db
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid OTP"


@pytest.mark.asyncio
async def test_verify_2fa_handles_exception(monkeypatch):
    """Verify 2FA surfaces unexpected errors as 500."""
    user = SimpleNamespace(is_2fa_enabled=True, otp_secret="secret")
    db = FakeDB()

    def boom(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(p2fa_router.TwoFactorAuth, "verify_totp", boom)
    with pytest.raises(HTTPException) as exc:
        await p2fa_router.verify_2fa(
            otp=SimpleNamespace(otp="123"), current_user=user, db=db
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "Error verifying two-factor authentication"
