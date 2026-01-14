"""Test module for test session13 banned words router."""
import pytest

from app import models, oauth2
from app.core.database import get_db
from app.modules.moderation.models import BannedWord
from app.routers import banned_words
from fastapi import FastAPI
from tests.testclient import TestClient


def _make_app(session, current_user):
    """Helper for  make app."""
    app = FastAPI()
    app.include_router(banned_words.router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[oauth2.get_current_user] = lambda: current_user
    return app


@pytest.fixture
def admin(session):
    """Pytest fixture for admin."""
    user = models.User(
        email="admin13@example.com",
        hashed_password="x",
        is_verified=True,
        is_admin=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_add_list_update_and_delete_banned_word(session, admin, monkeypatch):
    # Avoid pickle issues in cached wrapper during tests
    """Test case for test add list update and delete banned word."""
    monkeypatch.setattr(
        banned_words, "get_banned_words", banned_words.get_banned_words.__wrapped__
    )
    app = _make_app(session, admin)
    client = TestClient(app)

    add = client.post(
        "/banned-words/", json={"word": "spam", "severity": "warn", "is_regex": False}
    )
    assert add.status_code == 201
    word_id = add.json()["id"]

    listed = client.get("/banned-words/")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["words"][0]["word"] == "spam"

    upd = client.put(f"/banned-words/{word_id}", json={"severity": "ban"})
    assert upd.status_code == 200
    assert upd.json()["severity"] == "ban"

    delete = client.delete(f"/banned-words/{word_id}")
    assert delete.status_code == 200
    assert session.query(BannedWord).count() == 0


def test_duplicate_word_rejected(session, admin):
    """Test case for test duplicate word rejected."""
    app = _make_app(session, admin)
    client = TestClient(app)
    client.post(
        "/banned-words/", json={"word": "dupe", "severity": "warn", "is_regex": False}
    )

    dup = client.post(
        "/banned-words/", json={"word": "dupe", "severity": "warn", "is_regex": False}
    )
    assert dup.status_code == 400
    assert dup.json()["detail"] == "Word already exists in the banned list"


def test_bulk_insert_and_search_sort(session, admin, monkeypatch):
    """Test case for test bulk insert and search sort."""
    monkeypatch.setattr(
        banned_words, "get_banned_words", banned_words.get_banned_words.__wrapped__
    )
    app = _make_app(session, admin)
    client = TestClient(app)

    bulk = client.post(
        "/banned-words/bulk",
        json=[
            {"word": "alpha", "severity": "warn", "is_regex": False},
            {"word": "beta", "severity": "ban", "is_regex": False},
            {"word": "alphabet", "severity": "warn", "is_regex": True},
        ],
    )
    assert bulk.status_code == 201

    search = client.get(
        "/banned-words/",
        params={"search": "alpha", "sort_by": "created_at", "sort_order": "desc"},
    )
    assert search.status_code == 200
    data = search.json()
    assert data["total"] == 2
    assert all("alpha" in w["word"] for w in data["words"])


def test_non_admin_cannot_access(session):
    """Test case for test non admin cannot access."""
    user = models.User(
        email="user13@example.com",
        hashed_password="x",
        is_verified=True,
        is_admin=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    app = _make_app(session, user)
    client = TestClient(app)

    resp = client.get("/banned-words/")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Access denied: admin privileges required"
    resp_add = client.post(
        "/banned-words/", json={"word": "nope", "severity": "warn", "is_regex": False}
    )
    assert resp_add.status_code == 403
    assert resp_add.json()["detail"] == "Access denied: admin privileges required"
