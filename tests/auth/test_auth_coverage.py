"""Targeted auth coverage tests for previously missed branches."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import models, oauth2, schemas
from app.core.config import settings
from app.modules.utils.security import hash as hash_password
from app.modules.utils.security import verify
from app.routers import auth


def _make_user(session, email: str, password: str, **kwargs) -> models.User:
    is_verified = kwargs.pop("is_verified", True)
    user = models.User(
        email=email,
        hashed_password=hash_password(password),
        is_verified=is_verified,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _patch_fastmail(monkeypatch, sent):
    class DummyMailer:
        def __init__(self, config):
            self.config = config

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(auth, "FastMail", DummyMailer)


@contextmanager
def _symmetric_jwt():
    original_alg = settings.algorithm
    original_secret = settings.secret_key
    settings.algorithm = "HS256"
    settings.secret_key = "test-secret"
    try:
        yield
    finally:
        settings.algorithm = original_alg
        settings.secret_key = original_secret


def test_register_and_resend_verification_email(client, monkeypatch):
    sent = []
    _patch_fastmail(monkeypatch, sent)

    payload = {"email": "register@example.com", "password": "StrongPass123!"}
    with _symmetric_jwt():
        resp = client.post("/register", json=payload)
        assert resp.status_code == 201
        assert resp.json()["email"] == payload["email"]

        resend = client.post("/resend-verification", json={"email": payload["email"]})
        assert resend.status_code == 200
        assert "verification link" in resend.json()["message"].lower()
        assert sent


def test_login_suspended_user(client, session):
    user = _make_user(
        session,
        email="suspended@example.com",
        password="Pass123!",
        is_suspended=True,
    )
    resp = client.post("/login", data={"username": user.email, "password": "Pass123!"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account is suspended"


def test_login_locked_user_naive_timestamp(client, session):
    user = _make_user(session, email="locked@example.com", password="Pass123!")
    user.account_locked_until = datetime.now() + timedelta(hours=1)
    session.commit()

    resp = client.post("/login", data={"username": user.email, "password": "Pass123!"})
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()


def test_login_2fa_invalid_request(client, session):
    user = _make_user(session, email="no2fa@example.com", password="Pass123!")
    resp = client.post("/login/2fa", params={"user_id": user.id}, json={"otp": "000000"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid request"


def test_reset_password_request_and_reset_success(client, session, monkeypatch):
    sent = []
    _patch_fastmail(monkeypatch, sent)
    monkeypatch.setattr(auth, "timezone", SimpleNamespace(utc=None))

    user = _make_user(session, email="reset@example.com", password="OldPass123!")
    with _symmetric_jwt():
        resp = client.post("/reset-password-request", json={"email": user.email})
        assert resp.status_code == 200
        session.refresh(user)
        assert user.reset_token

        reset_resp = client.post(
            "/reset-password",
            json={"token": user.reset_token, "new_password": "NewPass123!"},
        )
        assert reset_resp.status_code == 200
        session.refresh(user)
        assert user.reset_token is None
        assert verify("NewPass123!", user.hashed_password)


def test_reset_password_invalid_token(client):
    resp = client.post(
        "/reset-password",
        json={"token": "not-a-token", "new_password": "NewPass123!"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired code"


def test_refresh_token_missing_and_session(client, session):
    original_secret = settings.refresh_secret_key
    original_alg = settings.refresh_algorithm
    settings.refresh_secret_key = "refresh-secret"
    settings.refresh_algorithm = "HS256"
    try:
        missing = client.post("/refresh-token")
        assert missing.status_code == 400

        user = _make_user(session, email="refresh@example.com", password="Pass123!")
        bad_token = oauth2.create_refresh_token(
            {"sub": str(user.id), "session_id": "missing-session"}
        )
        missing_session = client.post(
            "/refresh-token", json={"refresh_token": bad_token}
        )
        assert missing_session.status_code == 401
        assert missing_session.json()["detail"] == "Session not found"

        session_id = "sess-1"
        session.add(
            models.UserSession(
                user_id=user.id,
                session_id=session_id,
                ip_address="127.0.0.1",
                user_agent="pytest",
            )
        )
        session.commit()
        good_token = oauth2.create_refresh_token(
            {"sub": str(user.id), "session_id": session_id}
        )
        ok = client.post("/refresh-token", json={"refresh_token": good_token})
        assert ok.status_code == 200
        assert "access_token" in ok.json()
    finally:
        settings.refresh_secret_key = original_secret
        settings.refresh_algorithm = original_alg


def test_jwks_keys_success(client):
    resp = client.get("/jwks.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "keys" in data


def test_jwks_keys_symmetric_error(client):
    original_alg = settings.algorithm
    try:
        settings.algorithm = "HS256"
        resp = client.get("/jwks.json")
        assert resp.status_code == 400
        assert (
            resp.json()["detail"]
            == "JWKS not available for symmetric algorithms"
        )
    finally:
        settings.algorithm = original_alg


def test_verify_email_marks_user_verified(client, session):
    user = _make_user(
        session,
        email="verify@example.com",
        password="Pass123!",
        is_verified=False,
    )
    original_alg = settings.algorithm
    original_secret = settings.secret_key
    try:
        settings.algorithm = "HS256"
        settings.secret_key = "verify-secret"
        token = auth.create_verification_token(user.email)
        resp = client.post("/verify-email", params={"token": token})
        assert resp.status_code == 200
        session.refresh(user)
        assert user.is_verified is True
    finally:
        settings.algorithm = original_alg
        settings.secret_key = original_secret


def test_password_strength_endpoint(client):
    resp = client.post("/password-strength", params={"password": "Weakpass1!"})
    assert resp.status_code == 200
    assert "strength" in resp.json()


def test_change_password_endpoint(authorized_client, test_user, session, monkeypatch):
    monkeypatch.setattr(auth, "queue_email_notification", lambda *args, **kwargs: None)
    resp = authorized_client.post(
        "/change-password",
        json={"current_password": test_user["password"], "new_password": "NewPass123!"},
    )
    assert resp.status_code == 200
    updated = session.get(models.User, test_user["id"])
    assert verify("NewPass123!", updated.hashed_password)


def test_session_management_endpoints(authorized_client, test_user, session, monkeypatch):
    monkeypatch.setattr(oauth2, "get_client_ip", lambda request: "127.0.0.1")
    user = session.get(models.User, test_user["id"])
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            models.UserSession(
                user_id=user.id,
                session_id="sess-1",
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=now,
                last_activity=now,
            ),
            models.UserSession(
                user_id=user.id,
                session_id="sess-2",
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=now,
                last_activity=now,
            ),
        ]
    )
    session.commit()

    active = authorized_client.post("/sessions/active")
    assert active.status_code == 200
    session_id = active.json()[0]["session_id"]

    end = authorized_client.delete(f"/sessions/{session_id}")
    assert end.status_code == 200

    # cover direct session cleanup helpers
    auth.logout_all_devices(current_user=user, current_session="sess-2", db=session)
    remaining = (
        session.query(models.UserSession)
        .filter(models.UserSession.user_id == user.id)
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].session_id == "sess-2"

    asyncio.run(auth.invalidate_all_sessions(current_user=user, db=session))
    assert (
        session.query(models.UserSession)
        .filter(models.UserSession.user_id == user.id)
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_change_email_direct(session):
    user = _make_user(session, email="old@example.com", password="OldPass123!")
    _make_user(session, email="taken@example.com", password="OtherPass123!")

    with pytest.raises(Exception):
        await auth.change_email(
            SimpleNamespace(
                old_email=user.email,
                new_email="new@example.com",
                password="wrong",
            ),
            current_user=user,
            db=session,
        )

    with pytest.raises(Exception):
        await auth.change_email(
            SimpleNamespace(
                old_email=user.email,
                new_email="taken@example.com",
                password="OldPass123!",
            ),
            current_user=user,
            db=session,
        )

    resp = await auth.change_email(
        SimpleNamespace(
            old_email=user.email,
            new_email="new@example.com",
            password="OldPass123!",
        ),
        current_user=user,
        db=session,
    )
    assert resp["message"] == "Email changed successfully"
    assert user.email == "new@example.com"
    assert user.is_verified is False


@pytest.mark.asyncio
async def test_security_questions_flow_direct(monkeypatch):
    user = SimpleNamespace(
        id=1,
        email="sq@example.com",
        security_questions=None,
        reset_token=None,
        reset_token_expires=None,
    )

    class DummyQuery:
        def __init__(self, user_obj):
            self.user_obj = user_obj

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.user_obj

    class DummyDB:
        def __init__(self, user_obj):
            self.user_obj = user_obj
            self.committed = False

        def query(self, *args, **kwargs):
            return DummyQuery(self.user_obj)

        def commit(self):
            self.committed = True

    db = DummyDB(user)
    monkeypatch.setattr(auth, "log_user_event", lambda *args, **kwargs: None)

    questions = SimpleNamespace(
        questions=[
            SimpleNamespace(question="q1", answer="a1"),
            SimpleNamespace(question="q2", answer="a2"),
        ]
    )
    resp = await auth.set_security_questions(questions, current_user=user, db=db)
    assert resp["message"] == "Security questions set successfully"
    assert user.security_questions

    answers = [
        schemas.SecurityQuestionAnswer(question="q1", answer="a1"),
        schemas.SecurityQuestionAnswer(question="q2", answer="a2"),
    ]
    with _symmetric_jwt():
        verify_resp = await auth.verify_security_questions(
            answers, email=user.email, db=db
        )
        assert "reset_token" in verify_resp
