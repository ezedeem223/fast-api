"""Additional coverage for crypto helpers and oauth2 error branches."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from jose import JWTError
from fastapi import HTTPException

from app import crypto, oauth2
from app.core.config import settings
from app.modules.users import models as user_models


def test_crypto_key_serialization_and_ratchet():
    """Cover key generation, serialization, and ratchet updates."""
    priv, pub = crypto.generate_key_pair()
    pub_bytes = crypto.serialize_public_key(pub)
    priv_bytes = crypto.serialize_private_key(priv)

    restored_pub = crypto.deserialize_public_key(pub_bytes)
    restored_priv = crypto.deserialize_private_key(priv_bytes)

    assert restored_pub.public_bytes_raw() == pub_bytes
    assert restored_priv.private_bytes_raw() == priv_bytes

    alice = crypto.SignalProtocol()
    bob = crypto.SignalProtocol()
    alice.initial_key_exchange(bob.dh_pub)
    old_root = alice.root_key

    alice.ratchet(bob.dh_pub)
    assert alice.root_key != old_root
    assert alice.next_header_key is not None


def test_create_access_token_raises_on_key_failure(monkeypatch):
    """create_access_token should re-raise key lookup errors."""
    monkeypatch.setattr(
        settings.__class__,
        "get_jwt_key_id",
        lambda _self: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    with pytest.raises(RuntimeError):
        oauth2.create_access_token({"user_id": 1})


def test_create_refresh_token_requires_secret(monkeypatch):
    """create_refresh_token should raise when secrets are unset."""
    monkeypatch.setattr(settings, "refresh_secret_key", None, raising=False)
    monkeypatch.setattr(settings, "secret_key", None, raising=False)
    with pytest.raises(ValueError):
        oauth2.create_refresh_token({"user_id": 1})


def test_decode_access_token_invalid_header(monkeypatch):
    """_decode_access_token should handle invalid headers gracefully."""
    monkeypatch.setattr(settings.__class__, "get_jwt_public_keys", lambda _self: {})
    with pytest.raises(JWTError):
        oauth2._decode_access_token("not-a-jwt")


def test_get_current_session_missing_session_id(monkeypatch):
    """get_current_session should reject tokens without session_id."""
    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": 1})
    with pytest.raises(HTTPException):
        oauth2.get_current_session(token="token")


def test_verify_access_token_rejects_bad_user_id(monkeypatch):
    """verify_access_token should reject non-castable user_id values."""
    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": "bad"})
    exc = HTTPException(status_code=401, detail="bad")
    with pytest.raises(HTTPException):
        oauth2.verify_access_token("token", exc)


def test_get_current_user_bad_payloads(monkeypatch, session):
    """Cover get_current_user credential failures and user lookup."""
    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": None})
    with pytest.raises(HTTPException):
        oauth2.get_current_user(token="token", db=session, request=None)

    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": "bad"})
    with pytest.raises(HTTPException):
        oauth2.get_current_user(token="token", db=session, request=None)

    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: (_ for _ in ()).throw(JWTError("boom")))
    with pytest.raises(HTTPException):
        oauth2.get_current_user(token="token", db=session, request=None)

    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": 99999})
    with pytest.raises(HTTPException):
        oauth2.get_current_user(token="token", db=session, request=None)


def test_get_current_user_ip_evasion_and_ban(monkeypatch, session):
    """Exercise IP evasion logging and naive ban timestamps."""
    user = user_models.User(
        email="ban@example.com",
        hashed_password="x",
        is_verified=True,
        current_ban_end=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": user.id})
    monkeypatch.setattr(oauth2, "is_ip_banned", lambda *_: False)
    monkeypatch.setattr(oauth2, "detect_ip_evasion", lambda *_: True)
    monkeypatch.setattr(oauth2, "get_client_ip", lambda *_: "1.2.3.4")

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))
    with pytest.raises(HTTPException) as exc:
        oauth2.get_current_user(token="token", db=session, request=request)
    assert exc.value.status_code == 403
    assert exc.value.detail.startswith("User is banned until")


def test_get_current_user_handles_db_errors(monkeypatch):
    """Ensure unexpected DB errors return 500."""
    class BrokenSession:
        def query(self, *_):
            raise RuntimeError("db down")

    monkeypatch.setattr(oauth2, "_decode_access_token", lambda *_: {"user_id": 1})
    with pytest.raises(HTTPException) as exc:
        oauth2.get_current_user(token="token", db=BrokenSession(), request=None)
    assert exc.value.status_code == 500
    assert exc.value.detail == "Internal server error"
