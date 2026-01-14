"""Additional coverage for social_auth router branches."""

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import models, oauth2, schemas
from app.core.database import get_db
from app.routers import social_auth
from tests.testclient import TestClient


class DummyOAuthClient:
    """Stub OAuth client used for social auth tests."""

    def __init__(self, token=None, profile=None):
        self.token = token or {"access_token": "tok", "expires_in": 3600}
        self.profile = profile or {}
        self.redirect_uri = None

    async def authorize_redirect(self, request, redirect_uri):
        self.redirect_uri = str(redirect_uri)
        return JSONResponse({"redirect_to": self.redirect_uri})

    async def authorize_access_token(self, request):
        return self.token

    async def get(self, path, token=None):
        class Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        return Resp(self.profile)


class FakeQuery:
    """Minimal query stub that returns a fixed result."""

    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class FakeSession:
    """Minimal session stub for social auth router tests."""

    def __init__(self, result=None):
        self._result = result
        self.added = []
        self.committed = False
        self.refreshed = []

    def query(self, model):
        return FakeQuery(self._result)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 123
        self.refreshed.append(obj)


@contextmanager
def make_client(session, current_user=None):
    """Build a FastAPI app with social_auth router and overrides."""
    app = FastAPI()
    app.include_router(social_auth.router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    if current_user is not None:
        app.dependency_overrides[oauth2.get_current_user] = lambda: current_user
    with TestClient(app) as client:
        yield client


def test_login_twitter_redirect(monkeypatch):
    """Ensure login/twitter uses the expected redirect URI."""
    dummy_twitter = DummyOAuthClient()
    monkeypatch.setattr(
        social_auth,
        "oauth",
        SimpleNamespace(twitter=dummy_twitter),
        raising=False,
    )
    with make_client(FakeSession()) as client:
        resp = client.get("/login/twitter")
    assert resp.status_code == 200
    assert resp.json()["redirect_to"].endswith("/auth/twitter")
    assert dummy_twitter.redirect_uri.endswith("/auth/twitter")


def test_auth_twitter_creates_user(monkeypatch):
    """Twitter callback creates a new user when none exists."""
    dummy_twitter = DummyOAuthClient(
        profile={"id_str": "tw1", "screen_name": "bob"}
    )
    monkeypatch.setattr(
        social_auth,
        "oauth",
        SimpleNamespace(twitter=dummy_twitter),
        raising=False,
    )
    seen = {}

    def fake_token(data):
        seen["data"] = data
        return "tok-twitter"

    monkeypatch.setattr(social_auth.oauth2, "create_access_token", fake_token)

    class DummyUser:
        twitter_id = object()

        def __init__(self, **kwargs):
            self.id = None
            for key, value in kwargs.items():
                setattr(self, key, value)

    monkeypatch.setattr(social_auth.models, "User", DummyUser)
    fake_session = FakeSession(result=None)
    with make_client(fake_session) as client:
        resp = client.get("/auth/twitter")
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "tok-twitter"
    assert fake_session.committed is True
    assert fake_session.added
    created = fake_session.added[0]
    assert created.twitter_id == "tw1"
    assert created.username == "bob"
    assert seen["data"]["user_id"] == created.id


def test_auth_facebook_creates_user(monkeypatch):
    """Facebook callback creates a user and returns access token."""
    dummy_facebook = DummyOAuthClient(
        profile={"id": "fb1", "email": "fb@example.com"}
    )
    monkeypatch.setattr(
        social_auth,
        "oauth",
        SimpleNamespace(facebook=dummy_facebook),
        raising=False,
    )
    seen = {}

    def fake_token(data):
        seen["data"] = data
        return "tok-fb"

    monkeypatch.setattr(social_auth.oauth2, "create_access_token", fake_token)
    fake_session = FakeSession(result=None)
    with make_client(fake_session) as client:
        resp = client.get("/auth/facebook")
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "tok-fb"
    created = fake_session.added[0]
    assert created.email == "fb@example.com"
    assert created.facebook_id == "fb1"
    assert seen["data"]["user_id"] == created.id


def test_social_callback_reddit(monkeypatch):
    """Reddit callback stores linked account details."""
    dummy_reddit = DummyOAuthClient(
        token={"access_token": "rtok", "expires_in": 60, "refresh_token": "r1"},
        profile={"name": "reddit_user"},
    )
    monkeypatch.setattr(
        social_auth,
        "oauth",
        SimpleNamespace(reddit=dummy_reddit),
        raising=False,
    )
    fake_session = FakeSession()
    current_user = SimpleNamespace(id=7)
    with make_client(fake_session, current_user=current_user) as client:
        resp = client.get("/callback/reddit")
    assert resp.status_code == 200
    assert "connected successfully" in resp.json()["message"]
    account = fake_session.added[0]
    assert account.user_id == current_user.id
    assert account.platform == schemas.SocialMediaType.REDDIT
    assert account.account_username == "reddit_user"
    assert account.token_expires_at is not None


def test_social_callback_linkedin(monkeypatch):
    """LinkedIn callback stores display-friendly usernames."""
    dummy_linkedin = DummyOAuthClient(
        token={"access_token": "ltok", "expires_in": 120},
        profile={"localizedFirstName": "L", "localizedLastName": "I"},
    )
    monkeypatch.setattr(
        social_auth,
        "oauth",
        SimpleNamespace(linkedin=dummy_linkedin),
        raising=False,
    )
    fake_session = FakeSession()
    current_user = SimpleNamespace(id=22)
    with make_client(fake_session, current_user=current_user) as client:
        resp = client.get("/callback/linkedin")
    assert resp.status_code == 200
    account = fake_session.added[0]
    assert account.platform == schemas.SocialMediaType.LINKEDIN
    assert account.account_username == "L I"


def test_disconnect_social_account_not_found():
    """Disconnect returns 404 when no active account exists."""
    fake_session = FakeSession(result=None)
    current_user = SimpleNamespace(id=5)
    with make_client(fake_session, current_user=current_user) as client:
        resp = client.delete("/disconnect/reddit")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Account not found"


def test_disconnect_social_account_success():
    """Disconnect marks account inactive when it exists."""
    current_user = SimpleNamespace(id=11)
    account = models.SocialMediaAccount(
        user_id=current_user.id,
        platform=schemas.SocialMediaType.REDDIT,
        access_token="tok",
        token_expires_at=datetime.now(timezone.utc),
        account_username="ruser",
    )
    account.is_active = True
    fake_session = FakeSession(result=account)
    with make_client(fake_session, current_user=current_user) as client:
        resp = client.delete("/disconnect/reddit")
    assert resp.status_code == 200
    assert account.is_active is False
    assert fake_session.committed is True
