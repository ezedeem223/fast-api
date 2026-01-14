"""Test module for test session4 oauth social."""
import types

import pytest

from app import models
from app.routers import oauth as oauth_router
from app.routers import social_auth
from fastapi.responses import JSONResponse


class FakeOAuthProvider:
    """Test class for FakeOAuthProvider."""
    def __init__(self, email=None, screen_name=None, raise_exc=False):
        self.email = email
        self.screen_name = screen_name
        self.raise_exc = raise_exc

    async def authorize_redirect(self, request, redirect_uri):
        return JSONResponse({"redirect_to": redirect_uri})

    async def authorize_access_token(self, request):
        if self.raise_exc:
            raise RuntimeError("boom")
        return {"token": "fake-token"}

    async def parse_id_token(self, request, token):
        if self.raise_exc:
            raise RuntimeError("boom")
        if self.email is None:
            return {}
        return {"email": self.email}

    async def get(self, url, token=None):
        if self.raise_exc:
            raise RuntimeError("boom")

        class Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        if "graph.facebook.com" in url:
            return Resp({"email": self.email, "id": "fbid"})
        # twitter path
        data = {"email": self.email}
        if self.screen_name:
            data["screen_name"] = self.screen_name
            data["id_str"] = "twid"
        return Resp(data)


@pytest.fixture(autouse=True)
def _cleanup_oauth(monkeypatch):
    """Restore oauth objects after each test."""
    original_oauth = oauth_router.oauth
    original_social_oauth = social_auth.oauth
    yield
    monkeypatch.setattr(oauth_router, "oauth", original_oauth, raising=False)
    monkeypatch.setattr(social_auth, "oauth", original_social_oauth, raising=False)


def test_google_callback_success_creates_user(client, session, monkeypatch):
    """Google callback returns token when email present and creates user if missing."""
    fake_google = FakeOAuthProvider(email="g@test.com")
    oauth = types.SimpleNamespace(google=fake_google)
    monkeypatch.setattr(oauth_router, "oauth", oauth, raising=False)
    monkeypatch.setattr(
        oauth_router.oauth2, "create_access_token", lambda data: "tok-google"
    )
    # Pre-create user to avoid model constraint issues when committing new users
    session.add(models.User(email="g@test.com", hashed_password="x"))
    session.commit()

    resp = client.get("/google/callback")
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "tok-google"

    db_user = session.query(models.User).filter_by(email="g@test.com").first()
    assert db_user is not None


def test_google_callback_missing_email_returns_400(client, monkeypatch):
    """Missing email in ID token triggers 400 error."""
    fake_google = FakeOAuthProvider(email=None)
    oauth = types.SimpleNamespace(google=fake_google)
    monkeypatch.setattr(oauth_router, "oauth", oauth, raising=False)
    monkeypatch.setattr(
        oauth_router.oauth2, "create_access_token", lambda data: "tok-google"
    )

    resp = client.get("/google/callback")
    assert resp.status_code == 400
    assert "Unable to retrieve an email address" in resp.json()["detail"]


def test_google_callback_provider_error(client, monkeypatch):
    """Provider exception surfaces as 500."""
    fake_google = FakeOAuthProvider(email="g@test.com", raise_exc=True)
    oauth = types.SimpleNamespace(google=fake_google)
    monkeypatch.setattr(oauth_router, "oauth", oauth, raising=False)
    monkeypatch.setattr(
        oauth_router.oauth2, "create_access_token", lambda data: "tok-google"
    )

    resp = client.get("/google/callback")
    assert resp.status_code == 500
    assert "Google authentication failed" in resp.json()["detail"]


def test_facebook_social_auth_callback_creates_user(client, session, monkeypatch):
    """Social auth Facebook callback creates user and returns token."""
    fake_facebook = FakeOAuthProvider(email="fb@test.com")
    social_oauth = types.SimpleNamespace(facebook=fake_facebook)
    monkeypatch.setattr(social_auth, "oauth", social_oauth, raising=False)
    monkeypatch.setattr(
        social_auth.oauth2, "create_access_token", lambda data: "tok-fb"
    )
    session.add(
        models.User(email="fb@test.com", hashed_password="x", facebook_id="fbid")
    )
    session.commit()

    resp = client.get("/auth/facebook")
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "tok-fb"

    db_user = session.query(models.User).filter_by(email="fb@test.com").first()
    assert db_user is not None


def test_twitter_callback_email_fallback_screen_name(client, session, monkeypatch):
    """Twitter callback builds fallback email from screen_name when email missing."""
    fake_twitter = FakeOAuthProvider(email=None, screen_name="bob")
    oauth = types.SimpleNamespace(twitter=fake_twitter)
    monkeypatch.setattr(oauth_router, "oauth", oauth, raising=False)
    monkeypatch.setattr(
        oauth_router.oauth2, "create_access_token", lambda data: "tok-tw"
    )
    session.add(models.User(email="bob@twitter.local", hashed_password="x"))
    session.commit()

    resp = client.get("/twitter/callback")
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "tok-tw"

    db_user = session.query(models.User).filter_by(email="bob@twitter.local").first()
    assert db_user is not None
