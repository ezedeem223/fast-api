"""Additional coverage for OAuth router helpers and callbacks."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.routers import oauth as oauth_router


class DummyRequest:
    """Minimal request stub for url_for usage."""

    def __init__(self, url):
        self._url = url

    def url_for(self, _name):
        return self._url


class DummyOAuthClient:
    """Stub OAuth client with controllable responses."""

    def __init__(self, token=None, profile=None):
        self.token = token or {"token": "ok"}
        self.profile = profile or {}
        self.redirect_uri = None

    async def authorize_redirect(self, request, redirect_uri):
        self.redirect_uri = str(redirect_uri)
        return {"redirect_to": self.redirect_uri}

    async def authorize_access_token(self, request):
        return self.token

    async def parse_id_token(self, request, token):
        return self.profile

    async def get(self, _url, token=None):
        class Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        return Resp(self.profile)


def test_get_callback_url():
    """_get_callback_url returns the url_for result."""
    req = DummyRequest("https://example.com/callback")
    assert oauth_router._get_callback_url(req, "any") == "https://example.com/callback"


def test_issue_token_for_email_missing_email():
    """Missing email raises 400."""
    with pytest.raises(HTTPException) as exc:
        oauth_router._issue_token_for_email(db=SimpleNamespace(), email=None)
    assert exc.value.status_code == 400
    assert (
        exc.value.detail
        == "Unable to retrieve an email address from the OAuth provider."
    )


def test_issue_token_for_email_creates_user(monkeypatch):
    """When user missing, it is created and token returned."""

    class DummyUser:
        email = "email"

        def __init__(self, email, password, is_verified):
            self.email = email
            self.password = password
            self.is_verified = is_verified
            self.id = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeDB:
        def __init__(self):
            self.added = []
            self.committed = 0

        def query(self, model):
            return FakeQuery()

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            self.committed += 1

        def refresh(self, obj):
            obj.id = 7

    monkeypatch.setattr(oauth_router.models, "User", DummyUser)
    monkeypatch.setattr(oauth_router.oauth2, "create_access_token", lambda data: "tok")
    db = FakeDB()
    result = oauth_router._issue_token_for_email(db, "new@example.com")
    assert result["access_token"] == "tok"
    assert db.added


def test_issue_token_for_email_existing_user(monkeypatch):
    """Existing user path skips creation."""

    class FakeQuery:
        def __init__(self, user):
            self._user = user

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self._user

    class FakeDB:
        def query(self, model):
            return FakeQuery(SimpleNamespace(id=5, email="e@example.com"))

    monkeypatch.setattr(oauth_router.oauth2, "create_access_token", lambda data: "tok")
    result = oauth_router._issue_token_for_email(FakeDB(), "e@example.com")
    assert result["access_token"] == "tok"


@pytest.mark.asyncio
async def test_oauth_redirects(monkeypatch):
    """Google/Facebook/Twitter redirect endpoints return redirect."""
    dummy_google = DummyOAuthClient()
    dummy_facebook = DummyOAuthClient()
    dummy_twitter = DummyOAuthClient()
    monkeypatch.setattr(
        oauth_router,
        "oauth",
        SimpleNamespace(google=dummy_google, facebook=dummy_facebook, twitter=dummy_twitter),
        raising=False,
    )
    request = DummyRequest("https://cb")

    resp = await oauth_router.auth_google(request)
    assert resp["redirect_to"] == "https://cb"

    resp_fb = await oauth_router.auth_facebook(request)
    assert resp_fb["redirect_to"] == "https://cb"

    resp_tw = await oauth_router.auth_twitter(request)
    assert resp_tw["redirect_to"] == "https://cb"


@pytest.mark.asyncio
async def test_google_facebook_callbacks(monkeypatch):
    """Google and Facebook callbacks issue tokens."""
    dummy_google = DummyOAuthClient(profile={"email": "g@example.com"})
    dummy_facebook = DummyOAuthClient(profile={"email": "fb@example.com"})
    monkeypatch.setattr(
        oauth_router, "oauth", SimpleNamespace(google=dummy_google, facebook=dummy_facebook), raising=False
    )
    monkeypatch.setattr(oauth_router, "_issue_token_for_email", lambda _db, email: {"email": email})

    request = DummyRequest("https://cb")
    result = await oauth_router.auth_google_callback(request, db=SimpleNamespace())
    assert result["email"] == "g@example.com"

    result_fb = await oauth_router.auth_facebook_callback(request, db=SimpleNamespace())
    assert result_fb["email"] == "fb@example.com"


@pytest.mark.asyncio
async def test_twitter_callback_fallback_email(monkeypatch):
    """Twitter callback uses screen_name fallback when email missing."""
    dummy_twitter = DummyOAuthClient(profile={"screen_name": "bob"})
    monkeypatch.setattr(oauth_router, "oauth", SimpleNamespace(twitter=dummy_twitter), raising=False)
    captured = {}

    def fake_issue(_db, email):
        captured["email"] = email
        return {"email": email}

    monkeypatch.setattr(oauth_router, "_issue_token_for_email", fake_issue)
    request = DummyRequest("https://cb")

    result = await oauth_router.auth_twitter_callback(request, db=SimpleNamespace())
    assert result["email"] == "bob@twitter.local"
    assert captured["email"] == "bob@twitter.local"
