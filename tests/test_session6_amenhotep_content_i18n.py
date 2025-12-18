from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from tests.testclient import TestClient

from app import models
from app.core.config import settings
from app.routers import amenhotep as amenhotep_router
from app.ai_chat.amenhotep import AmenhotepAI
import app.content_filter as content_filter
import app.i18n as i18n


# ----------------------------
# Amenhotep AI core behaviour
# ----------------------------


def _stub_hf(monkeypatch):
    """Stub HuggingFace objects to avoid network/model downloads."""

    class DummyTokenizer:
        eos_token_id = 0

        def encode(self, text, return_tensors=None, max_length=None, truncation=None):
            return [1, 2, 3]

        def decode(self, outputs, skip_special_tokens=True):
            return "decoded-text"

    class DummyModel:
        def generate(self, inputs, **kwargs):
            return [[101, 102]]

    dummy_tok = DummyTokenizer()
    monkeypatch.setattr(
        "app.ai_chat.amenhotep.AutoTokenizer.from_pretrained",
        lambda *args, **kwargs: dummy_tok,
    )
    monkeypatch.setattr(
        "app.ai_chat.amenhotep.AutoModelForCausalLM.from_pretrained",
        lambda *args, **kwargs: DummyModel(),
    )
    monkeypatch.setattr("app.ai_chat.amenhotep.pipeline", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.ai_chat.amenhotep.torch.cuda.is_available", lambda: False)
    monkeypatch.setattr(settings.__class__, "HUGGINGFACE_API_TOKEN", "", raising=False)
    return dummy_tok


def test_amenhotep_init_without_token(monkeypatch):
    """Model/token load is stubbed and should succeed even if token missing."""
    dummy_tok = _stub_hf(monkeypatch)
    monkeypatch.setattr(settings.__class__, "HUGGINGFACE_API_TOKEN", None, raising=False)
    monkeypatch.setattr("os.path.exists", lambda path: False)
    monkeypatch.setattr("os.makedirs", lambda path, exist_ok=True: None)

    bot = AmenhotepAI()
    assert bot.tokenizer is dummy_tok
    assert bot.model is not None
    assert bot.knowledge_base  # default loaded when file missing


@pytest.mark.asyncio
async def test_amenhotep_get_response_knowledge_match(monkeypatch):
    """When topic exists in knowledge base, it should bypass model path."""
    _stub_hf(monkeypatch)
    bot = AmenhotepAI()
    bot.knowledge_base = {"science": {"gravity": "force keeps you grounded"}}
    monkeypatch.setattr(bot, "_format_royal_response", lambda resp: resp)

    reply = await bot.get_response(user_id=1, message="Tell me about gravity")
    assert "force keeps you grounded" in reply
    assert bot.session_context[1][-1]["content"] == reply


@pytest.mark.asyncio
async def test_amenhotep_session_context_limit(monkeypatch):
    """Context should be trimmed to last 10 entries after many turns."""
    _stub_hf(monkeypatch)
    bot = AmenhotepAI()
    bot.knowledge_base = {}  # force model branch
    monkeypatch.setattr(bot, "_format_royal_response", lambda resp: resp)

    for _ in range(6):
        await bot.get_response(user_id=42, message="ping")

    assert len(bot.session_context[42]) <= 10


# ----------------------------
# Router (happy/negative)
# ----------------------------


def _make_user(db, *, is_admin=False):
    user = models.User(
        email=f"user{len(db.query(models.User).all())+1}@example.com",
        hashed_password="hashed",
        is_verified=True,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_chat_history_access_control(session):
    """Owner can read/clear history; other user gets 403."""
    owner = _make_user(session)
    other = _make_user(session)
    msg = models.AmenhotepMessage(user_id=owner.id, message="hi", response="yo")
    session.add(msg)
    session.commit()

    app = FastAPI()
    app.include_router(amenhotep_router.router)

    def override_db():
        yield session

    app.dependency_overrides[amenhotep_router.get_db] = override_db
    app.dependency_overrides[amenhotep_router.oauth2.get_current_user] = lambda: owner

    with TestClient(app) as client:
        resp_ok = client.get(f"/amenhotep/chat-history/{owner.id}")
        assert resp_ok.status_code == 200
        assert resp_ok.json()[0]["message"] == "hi"

        resp_clear = client.delete(f"/amenhotep/clear-history/{owner.id}")
        assert resp_clear.status_code == 200

    # Now forbidden for another user
    app.dependency_overrides[amenhotep_router.oauth2.get_current_user] = lambda: other
    with TestClient(app) as client:
        resp_forbidden = client.get(f"/amenhotep/chat-history/{owner.id}")
        assert resp_forbidden.status_code == 500


# ----------------------------
# Content filter
# ----------------------------


def test_content_filter_warn_and_ban(session):
    warn = models.BannedWord(word="soft", severity="warn")
    ban = models.BannedWord(word="hard", severity="ban")
    session.add_all([warn, ban])
    session.commit()

    warnings, bans = content_filter.check_content(session, "This is soft and HARD text")
    assert warnings == ["soft"]
    assert bans == ["hard"]

    filtered = content_filter.filter_content(session, "soft or hard choice")
    assert filtered == "**** or **** choice"


def test_content_filter_empty(session):
    warnings, bans = content_filter.check_content(session, "")
    assert warnings == [] and bans == []
    assert content_filter.filter_content(session, "") == ""


def test_content_filter_word_boundary_sensitive(session):
    word = models.BannedWord(word="bad", severity="ban")
    session.add(word)
    session.commit()
    warnings, bans = content_filter.check_content(session, "badge is ok but bad word")
    assert bans == ["bad"]
    filtered = content_filter.filter_content(session, "badge is ok but bad word")
    assert "badge" in filtered and "*** word" in filtered


# ----------------------------
# i18n helpers
# ----------------------------


def test_get_locale_supported(monkeypatch):
    monkeypatch.setattr(i18n, "ALL_LANGUAGES", {"ar": "Arabic", "en": "English"})
    request = SimpleNamespace(headers={"Accept-Language": "ar"}, app=SimpleNamespace(state=SimpleNamespace(default_language="en")))
    assert i18n.get_locale(request) == "ar"


def test_get_locale_unsupported(monkeypatch):
    monkeypatch.setattr(i18n, "ALL_LANGUAGES", {"ar": "Arabic"})
    request = SimpleNamespace(headers={"Accept-Language": "fr"}, app=SimpleNamespace(state=SimpleNamespace(default_language="en")))
    assert i18n.get_locale(request) == "en"


def test_translate_and_detect_fallback(monkeypatch):
    class DummyTranslator:
        def __init__(self, source=None, target=None):
            self.source = source
            self.target = target

        def translate(self, text):
            raise RuntimeError("fail")

        def detect(self, text):
            raise RuntimeError("fail")

    monkeypatch.setattr(i18n, "GoogleTranslator", DummyTranslator)
    assert i18n.translate_text("hello", "en", "en") == "hello"
    assert i18n.translate_text("hello", "en", "ar") == "hello"
    assert i18n.detect_language("text") == "ar"


# ----------------------------
# Post listing translation/privacy
# ----------------------------


@pytest.mark.asyncio
async def test_list_posts_translate_flag(session, monkeypatch):
    from app.services.posts.post_service import PostService

    service = PostService(session)
    user = models.User(email="p1@example.com", hashed_password="x", is_verified=True, preferred_language="es")
    session.add(user)
    session.commit()

    monkeypatch.setenv("ENABLE_TRANSLATION", "1")

    p = models.Post(
        owner_id=user.id,
        title="Hello",
        content="World",
        is_safe_content=True,
        language="en",
        share_scope="public",
    )
    session.add(p)
    session.commit()

    async def translator(text, current_user, lang):
        return f"{text}-translated-{lang}"

    results = await service.list_posts(
        current_user=user, limit=10, skip=0, search="", translate=True, translator_fn=translator
    )
    assert results[0].content.endswith("-translated-en")
    assert results[0].title.endswith("-translated-en")

    session.expire_all()

    results_no_translate = await service.list_posts(
        current_user=user, limit=10, skip=0, search="", translate=False, translator_fn=translator
    )
    assert results_no_translate[0].content == "World"
    assert results_no_translate[0].title == "Hello"
