import pytest
from fastapi import FastAPI

from tests.testclient import TestClient

from app import i18n, models
from app.modules.utils import links as utils_links
from app.modules.utils import search as utils_search
from app.routers import amenhotep as amenhotep_router


def test_extract_links_variations():
    assert utils_links.extract_links("no links here") == []

    mixed = "ftp://example.com and http://ok.com plus https://secure.test/page"
    assert utils_links.extract_links(mixed) == [
        "http://ok.com",
        "https://secure.test/page",
    ]


def test_spell_suggestions_ignore_invalid_tokens(monkeypatch):
    class DummySpell:
        def __contains__(self, word):
            return False

        def correction(self, word):
            return f"{word}_fix"

    monkeypatch.setattr(utils_search, "spell", DummySpell())

    assert utils_search.get_spell_suggestions("") == []
    assert utils_search.get_spell_suggestions("   ") == []
    assert utils_search.get_spell_suggestions("hello 123") == ["hello_fix"]


def _create_user(session, preferred_language="zz"):
    user = models.User(
        email=f"amenhotep{session.query(models.User).count()+1}@example.com",
        hashed_password="hashed",
        is_verified=True,
        preferred_language=preferred_language,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class DummyAmenhotep:
    welcome_message = "hello"

    async def get_response(self, user_id, message):
        return f"echo:{message}"


def _build_app(session, user, monkeypatch, default_lang="en"):
    monkeypatch.setattr(amenhotep_router, "AmenhotepAI", DummyAmenhotep)
    monkeypatch.setattr(i18n, "ALL_LANGUAGES", {"en": "English", "ar": "Arabic"})

    app = FastAPI()
    app.state.default_language = default_lang
    app.include_router(amenhotep_router.router)

    def override_db():
        yield session

    app.dependency_overrides[amenhotep_router.get_db] = override_db
    app.dependency_overrides[amenhotep_router.oauth2.get_current_user] = lambda: user
    return app


def test_ask_invalid_input_returns_422(session, monkeypatch):
    user = _create_user(session)
    app = _build_app(session, user, monkeypatch)

    with TestClient(app) as client:
        resp = client.post("/amenhotep/ask", json={})
        assert resp.status_code == 422


def test_ask_rejects_empty_text(session, monkeypatch):
    user = _create_user(session)
    app = _build_app(session, user, monkeypatch)

    with TestClient(app) as client:
        resp = client.post("/amenhotep/ask", json={"message": "   "})
        assert resp.status_code == 422


def test_ask_language_fallback_uses_default(session, monkeypatch):
    user = _create_user(session, preferred_language="xx")
    app = _build_app(session, user, monkeypatch, default_lang="ar")

    with TestClient(app) as client:
        resp = client.post("/amenhotep/ask", json={"message": "hello"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "ar"
    assert body["response"] == "echo:hello"
    assert body["id"] > 0
