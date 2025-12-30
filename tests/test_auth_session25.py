import datetime
from types import SimpleNamespace

import pytest
from jose import jwt

from app import models
from app.routers import auth


class DummyRequest:
    def __init__(self):
        self.client = SimpleNamespace(host="127.0.0.1")
        self.headers = {"user-agent": "pytest"}


def _user(session, email="user@example.com"):
    user = models.User(
        email=email,
        hashed_password="hashed",
        is_verified=True,
        failed_login_attempts=0,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_login_success(monkeypatch, session):
    user = _user(session)
    bg = auth.BackgroundTasks()

    class DummyForm:
        username = user.email
        password = "good"

    monkeypatch.setattr(auth, "verify", lambda password, hashed: password == "good")
    monkeypatch.setattr(auth.oauth2, "create_access_token", lambda data: "token123")
    monkeypatch.setattr(auth, "send_login_notification", lambda *a, **k: None)

    resp = auth.login(DummyRequest(), DummyForm(), session, bg)
    assert resp["access_token"] == "token123"
    assert resp["token_type"] == "bearer"


def test_login_locked_account(session, monkeypatch):
    user = _user(session, "locked@example.com")
    user.account_locked_until = datetime.datetime(2099, 1, 1)
    session.commit()

    class DummyForm:
        username = user.email
        password = "any"

    class NaiveDatetime:
        timezone = datetime.timezone

        @staticmethod
        def now(tz=None):
            return datetime.datetime(2000, 1, 1)

    monkeypatch.setattr(auth, "datetime", NaiveDatetime)
    monkeypatch.setattr(auth, "verify", lambda *a, **k: True)

    with pytest.raises(auth.HTTPException) as exc:
        auth.login(DummyRequest(), DummyForm(), session)
    assert exc.value.status_code == 403


def test_login_invalid_credentials_increments(session, monkeypatch):
    user = _user(session, "invalid@example.com")

    class DummyForm:
        username = user.email
        password = "bad"

    monkeypatch.setattr(auth, "verify", lambda pw, hashed: False)

    with pytest.raises(auth.HTTPException) as exc:
        auth.login(DummyRequest(), DummyForm(), session)
    assert exc.value.status_code == 403
    session.refresh(user)
    assert user.failed_login_attempts >= 1


@pytest.mark.asyncio
async def test_refresh_token_invalid_format(session):
    with pytest.raises(auth.HTTPException) as exc:
        await auth.refresh_token("not_a_token", session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_valid(monkeypatch, session):
    user = _user(session, "refresh@example.com")
    monkeypatch.setattr(auth.settings, "algorithm", "HS256")
    monkeypatch.setattr(auth.settings, "refresh_secret_key", "refresh-secret")
    token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=5),
        },
        auth.settings.refresh_secret_key,
        algorithm=auth.settings.algorithm,
    )
    monkeypatch.setattr(auth.oauth2, "create_access_token", lambda data: "new_access")
    result = await auth.refresh_token(token, session)
    assert result["access_token"] == "new_access"
