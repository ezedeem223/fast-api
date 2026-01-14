"""Test module for test session3 auth p2fa middleware."""
import asyncio
import json

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import models
from app.core import exceptions as app_exceptions
from app.core.middleware import language as language_mw
from app.modules.utils.security import hash as hash_password
from app.routers import p2fa


def _make_user(session, email="p2fa@example.com"):
    """Helper for  make user."""
    user = models.User(
        email=email,
        hashed_password=hash_password("pass"),
        is_verified=True,
        preferred_language="fr",
        auto_translate=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_p2fa_enable_disable_and_verify(client, session, monkeypatch):
    """Test case for test p2fa enable disable and verify."""
    user = _make_user(session)
    user.is_2fa_enabled = False
    user.otp_secret = None
    session.commit()
    session.refresh(user)
    client.app.dependency_overrides[p2fa.oauth2.get_current_user] = lambda: user
    monkeypatch.setattr(p2fa, "generate_qr_code", lambda uri: "qr-code")

    # enable 2FA succeeds
    enable_resp = client.post("/2fa/enable")
    assert enable_resp.status_code == 200
    data = enable_resp.json()
    assert "otp_secret" in data and data["otp_secret"]

    # verify succeeds with valid code
    secret = data["otp_secret"]
    valid_otp = p2fa.pyotp.TOTP(secret).now()
    verify_ok = client.post("/2fa/verify", json={"otp": valid_otp})
    assert verify_ok.status_code == 200

    # invalid OTP should surface as error (implementation wraps as 500)
    bad = client.post("/2fa/verify", json={"otp": "000000"})
    assert bad.status_code >= 400

    # disable 2FA succeeds
    disable = client.post("/2fa/disable")
    assert disable.status_code == 200

    client.app.dependency_overrides.pop(p2fa.oauth2.get_current_user, None)


def test_language_middleware_translation(monkeypatch):
    # make fake response
    """Test case for test language middleware translation."""
    class FakeResponse(JSONResponse):
        async def json(self):
            return {"msg": "hello"}

    async def call_next(_):
        return FakeResponse({"msg": "hello"})

    user = type("U", (), {"auto_translate": True, "preferred_language": "es"})

    async def fake_translate_text(text, src, target):
        return f"{target}:{text}"

    monkeypatch.setattr(language_mw, "translate_text", fake_translate_text)

    scope = {"type": "http", "headers": [], "client": ("1.1.1.1", 1234)}
    request = Request(scope)
    request.state.user = user
    result = asyncio.run(language_mw.language_middleware(request, call_next))
    assert json.loads(result.body)["msg"] == "es:hello"

    # auto_translate off => passthrough
    user.auto_translate = False
    result2 = asyncio.run(language_mw.language_middleware(request, call_next))
    assert json.loads(result2.body)["msg"] == "hello"


def test_app_exceptions_shapes():
    """Test case for test app exceptions shapes."""
    exc = app_exceptions.InvalidCredentialsException()
    assert exc.status_code == 401
    assert exc.detail["error_code"] == "invalid_credentials"

    with pytest.raises(app_exceptions.ResourceNotFoundException):
        app_exceptions.raise_not_found("Item", identifier=123)


def test_crypto_signal_protocol_round_trip_and_missing_keys():
    # Restore crypto module in case other tests patched it
    """Test case for test crypto signal protocol round trip and missing keys."""
    import importlib

    import app.crypto as crypto_mod

    importlib.reload(crypto_mod)
    crypto = crypto_mod
    # successful exchange and encrypt/decrypt
    a = crypto.SignalProtocol()
    b = crypto.SignalProtocol()
    a.initial_key_exchange(b.dh_pub)
    b.initial_key_exchange(a.dh_pub)
    plaintext = "hi there"
    encrypted = a.encrypt_message(plaintext)
    decrypted = b.decrypt_message(encrypted)
    assert decrypted == plaintext

    # missing chain key should fail
    c = crypto.SignalProtocol()
    with pytest.raises(Exception):
        c.encrypt_message("oops")
