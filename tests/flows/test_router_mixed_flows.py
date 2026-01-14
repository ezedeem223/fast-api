"""Test module for test routers session7."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest

from app import models, schemas
from app.ai_chat import amenhotep as amenhotep_module
from app.core.config import settings
from app.modules.search import typesense_client as ts_client
from app.modules.utils.security import hash as hash_password
from app.routers import oauth as oauth_router
from app.services.messaging import MessageService
from fastapi import HTTPException


def test_auth_login_lockout_triggers_after_failures(session, client):
    """Test case for test auth login lockout triggers after failures."""
    email = "lock@example.com"
    user = models.User(
        email=email,
        hashed_password=hash_password("correct"),
        is_verified=True,
        failed_login_attempts=0,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    for _ in range(5):
        resp = client.post(
            "/login",
            data={"username": email, "password": "wrong"},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 403

    refreshed = session.query(models.User).filter_by(email=email).first()
    assert refreshed.failed_login_attempts >= 5
    assert refreshed.account_locked_until is not None


def test_two_factor_enable_verify_and_login_flow(authorized_client, session, test_user):
    """Test case for test two factor enable verify and login flow."""
    enable_resp = authorized_client.post("/2fa/enable")
    assert enable_resp.status_code == 200
    secret = enable_resp.json()["otp_secret"]
    user_row = session.query(models.User).filter_by(email=test_user["email"]).first()
    user_row.is_2fa_enabled = True
    user_row.otp_secret = secret
    session.commit()
    session.refresh(user_row)
    totp = pyotp.TOTP(secret)
    good_code = totp.now()

    verify_resp = authorized_client.post("/2fa/verify", json={"otp": good_code})
    assert verify_resp.status_code == 200

    # enable route already set is_2fa_enabled/otp_secret
    wrong_code = "000000"
    login_resp = authorized_client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 200
    user_id = test_user["id"]

    bad_2fa = authorized_client.post(
        "/login/2fa", params={"user_id": user_id}, json={"otp": wrong_code}
    )
    assert bad_2fa.status_code in (400, 401)

    good_2fa = authorized_client.post(
        "/login/2fa", params={"user_id": user_id}, json={"otp": totp.now()}
    )
    assert good_2fa.status_code == 200
    assert good_2fa.json()["access_token"]


def test_social_auth_expired_token_returns_401(client, monkeypatch):
    """Test case for test social auth expired token returns 401."""
    async def expired_token(_request):
        raise HTTPException(status_code=401, detail="token expired")

    monkeypatch.setattr(
        oauth_router.oauth.twitter,
        "authorize_access_token",
        expired_token,
        raising=True,
    )
    resp = client.get("/twitter/callback")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token expired"


def test_post_upload_missing_file_returns_422(authorized_client):
    """Test case for test post upload missing file returns 422."""
    resp = authorized_client.post("/posts/upload_file/")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any("file" in err["loc"] for err in detail)


def test_message_audio_unsupported_format_returns_400(authorized_client, test_user2):
    """Test case for test message audio unsupported format returns 400."""
    files = {"audio_file": ("bad.txt", b"x", "text/plain")}
    resp = authorized_client.post(
        "/message/audio", data={"receiver_id": test_user2["id"]}, files=files
    )
    assert resp.status_code in (400, 422)
    if resp.status_code == 400:
        assert resp.json()["detail"] == "Unsupported audio format"


def test_notifications_invalid_filter_returns_422(authorized_client):
    """Test case for test notifications invalid filter returns 422."""
    resp = authorized_client.get("/notifications/", params={"category": "invalid"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any("category" in err["loc"] for err in detail)


def test_search_uses_sqlite_when_typesense_disabled(monkeypatch, authorized_client):
    """Test case for test search uses sqlite when typesense disabled."""
    monkeypatch.setattr(settings, "typesense_enabled", False)
    monkeypatch.setattr(ts_client, "_cached_client", None, raising=False)
    resp = authorized_client.post(
        "/search/", json={"query": "hello", "sort_by": "relevance"}
    )
    assert resp.status_code == 200
    assert "results" in resp.json()


def test_search_fallback_on_typesense_failure(monkeypatch, authorized_client):
    """Test case for test search fallback on typesense failure."""
    class FailingClient:
        def search_posts(self, *_, **__):
            raise RuntimeError("typesense down")

    monkeypatch.setattr(settings, "typesense_enabled", True)
    monkeypatch.setattr(ts_client, "_cached_client", FailingClient(), raising=False)
    resp = authorized_client.post(
        "/search/", json={"query": "fallback", "sort_by": "relevance"}
    )
    assert resp.status_code == 200
    assert "results" in resp.json()


def test_blocked_user_cannot_send_message(session):
    """Test case for test blocked user cannot send message."""
    sender = models.User(
        email="sender@example.com", hashed_password="x", is_verified=True
    )
    receiver = models.User(
        email="receiver@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([sender, receiver])
    session.commit()
    session.refresh(sender)
    session.refresh(receiver)

    block = models.Block(
        blocker_id=receiver.id,
        blocked_id=sender.id,
        block_type=models.BlockType.FULL,
        created_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(block)
    session.commit()

    svc = MessageService(session)
    with pytest.raises(HTTPException):
        asyncio.run(
            svc.create_message(
                payload=schemas.MessageCreate(
                    content="hi",
                    receiver_id=receiver.id,
                    message_type=schemas.MessageType.TEXT,
                ),
                current_user=sender,
                background_tasks=SimpleNamespace(add_task=lambda *_, **__: None),
            )
        )


def test_amenhotep_fallback_limits_history(monkeypatch):
    """Test case for test amenhotep fallback limits history."""
    class DummyAmenhotep:
        def __init__(self):
            self.session_context = {}

        async def get_response(self, user_id: int, message: str) -> str:
            history = self.session_context.setdefault(user_id, [])
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "fallback"})
            if len(history) > 10:
                self.session_context[user_id] = history[-10:]
            return "fallback"

    monkeypatch.setattr(amenhotep_module, "AmenhotepAI", DummyAmenhotep)
    bot = amenhotep_module.AmenhotepAI()
    for i in range(12):
        asyncio.run(bot.get_response(1, f"topic {i}"))
    assert len(bot.session_context[1]) == 10
    assert bot.session_context[1][-1]["content"] == "fallback"
