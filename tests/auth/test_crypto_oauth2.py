"""Test module for test session19 crypto oauth2."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import models, oauth2
from app.core.config.settings import Settings
from fastapi import HTTPException


def test_create_and_verify_access_token_roundtrip():
    """Test case for test create and verify access token roundtrip."""
    token = oauth2.create_access_token({"user_id": 123, "session_id": "sess1"})
    token_data = oauth2.verify_access_token(
        token, HTTPException(status_code=401, detail="bad")
    )
    assert token_data.id == 123

    session_id = oauth2.get_current_session(token)
    assert session_id == "sess1"


def test_create_access_token_invalid_user_id():
    """Test case for test create access token invalid user id."""
    with pytest.raises(ValueError):
        oauth2.create_access_token({"user_id": "not-an-int"})


def test_verify_access_token_missing_user_id_raises():
    """Test case for test verify access token missing user id raises."""
    token = oauth2.create_access_token({"foo": "bar"})
    with pytest.raises(HTTPException):
        oauth2.verify_access_token(token, HTTPException(status_code=401, detail="bad"))


def test_get_current_user_blacklisted_and_banned(session):
    """Test case for test get current user blacklisted and banned."""
    user = models.User(
        email="auth19@example.com", hashed_password="x", is_verified=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = oauth2.create_access_token({"user_id": user.id})

    # Blacklisted token should reject
    session.add(models.TokenBlacklist(token=token))
    session.commit()
    with pytest.raises(HTTPException) as exc:
        oauth2.get_current_user(token=token, db=session, request=None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been invalidated"

    # Remove from blacklist and mark user banned -> 403
    session.query(models.TokenBlacklist).delete()
    session.commit()
    user.current_ban_end = datetime.now(timezone.utc) + timedelta(hours=1)
    session.commit()
    with pytest.raises(HTTPException) as exc2:
        oauth2.get_current_user(token=token, db=session, request=None)
    assert exc2.value.status_code == 403
    assert exc2.value.detail.startswith("User is banned until")


def test_get_current_user_ip_banned(session):
    """Test case for test get current user ip banned."""
    user = models.User(email="ip19@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add(
        models.IPBan(
            ip_address="9.9.9.9",
            reason="test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    session.commit()

    token = oauth2.create_access_token({"user_id": user.id})
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="9.9.9.9"))
    with pytest.raises(HTTPException) as exc:
        oauth2.get_current_user(token=token, db=session, request=request)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Your IP address is banned"


def test_key_loading_validations(tmp_path, monkeypatch):
    # Valid key files succeed
    """Test case for test key loading validations."""
    for key in [
        "RSA_PRIVATE_KEY",
        "RSA_PUBLIC_KEY",
        "RSA_PRIVATE_KEY_PEM",
        "RSA_PUBLIC_KEY_PEM",
    ]:
        monkeypatch.delenv(key, raising=False)
    priv = tmp_path / "priv.pem"
    pub = tmp_path / "pub.pem"
    priv.write_text("PRIVATE KEY DATA")
    pub.write_text("PUBLIC KEY DATA")
    s = Settings(rsa_private_key_path=str(priv), rsa_public_key_path=str(pub))
    assert s.rsa_private_key == "PRIVATE KEY DATA"
    assert s.rsa_public_key == "PUBLIC KEY DATA"

    # Missing file raises
    with pytest.raises(ValueError):
        Settings(
            rsa_private_key_path=str(tmp_path / "missing.pem"),
            rsa_public_key_path=str(pub),
        )

    # Empty file raises
    empty = tmp_path / "empty.pem"
    empty.write_text("")
    with pytest.raises(ValueError):
        Settings(rsa_private_key_path=str(empty), rsa_public_key_path=str(pub))
