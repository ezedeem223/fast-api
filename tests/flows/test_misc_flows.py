"""Test module for test session8 misc."""
import asyncio
import io
import os
from datetime import datetime, timedelta

import pytest
from starlette.datastructures import UploadFile

from app import analytics, models
from app.ai_chat import amenhotep as amenhotep_module
from app.core.cache.redis_cache import cache_manager
from app.core.database import get_db
from app.core.database.query_helpers import cursor_paginate, paginate_query
from app.modules.community.models import SearchStatistics
from app.services.messaging import MessageService
from fastapi import HTTPException


def test_analytics_lazy_pipeline_cached(monkeypatch):
    """Test case for test analytics lazy pipeline cached."""
    created = object()

    class DummyPipeline:
        def __call__(self, text):
            return [{"label": "POSITIVE", "score": 0.9}]

    monkeypatch.setattr(analytics, "_sentiment_pipeline", None)
    monkeypatch.setattr(analytics, "pipeline", lambda *_, **__: DummyPipeline())
    monkeypatch.setattr(
        analytics,
        "AutoTokenizer",
        type("Tok", (), {"from_pretrained": lambda *_: None}),
    )
    monkeypatch.setattr(
        analytics,
        "AutoModelForSequenceClassification",
        type("Mod", (), {"from_pretrained": lambda *_: created}),
    )

    first = analytics._get_sentiment_pipeline()
    second = analytics._get_sentiment_pipeline()
    assert first is second


def test_suggest_improvements_boundary_word_count():
    """Test case for test suggest improvements boundary word count."""
    nine_words = "one two three four five six seven eight nine"
    ten_words = "one two three four five six seven eight nine ten"
    short = analytics.suggest_improvements(
        nine_words, {"sentiment": "POSITIVE", "score": 0.1}
    )
    assert "short" in short.lower()
    long = analytics.suggest_improvements(
        ten_words, {"sentiment": "POSITIVE", "score": 0.1}
    )
    assert "looks good" in long.lower()


def test_suggest_improvements_negative_threshold():
    """Test case for test suggest improvements negative threshold."""
    long_text = "one two three four five six seven eight nine ten eleven"
    suggestion = analytics.suggest_improvements(
        long_text, {"sentiment": "NEGATIVE", "score": 0.8}
    )
    assert "looks good" in suggestion.lower()


def test_clean_old_statistics(session):
    """Test case for test clean old statistics."""
    recent = SearchStatistics(
        user_id=1,
        term="keep",
        searches=1,
        updated_at=datetime.now(),
    )
    old = SearchStatistics(
        user_id=1,
        term="drop",
        searches=1,
        updated_at=datetime.now() - timedelta(days=5),
    )
    session.add_all([recent, old])
    session.commit()

    analytics.clean_old_statistics(session, days=2)
    remaining_terms = [s.term for s in session.query(models.SearchStatistics).all()]
    assert "drop" not in remaining_terms and "keep" in remaining_terms


def test_amenhotep_load_fallback(monkeypatch):
    """Test case for test amenhotep load fallback."""
    monkeypatch.setattr(os.path, "exists", lambda *_: False)
    kb = amenhotep_module.AmenhotepAI._load_knowledge_base(None)
    assert isinstance(kb, dict)
    assert kb


def test_amenhotep_expand_knowledge_base_writes(monkeypatch, tmp_path):
    """Test case for test amenhotep expand knowledge base writes."""
    class DummyAI:
        def __init__(self):
            self.knowledge_base = {"old": {"topic": "data"}}
            self.saved = False

        def _save_knowledge_base(self):
            self.saved = True

    bot = DummyAI()
    amenhotep_module.AmenhotepAI.expand_knowledge_base(
        bot, {"old": {"newtopic": "x"}, "newcat": {"topic": "y"}}
    )
    assert bot.knowledge_base["old"]["newtopic"] == "x"
    assert "newcat" in bot.knowledge_base
    assert bot.saved is True


def test_media_processing_rejects_large_attachment(session):
    """Test case for test media processing rejects large attachment."""
    service = MessageService(session)
    big_bytes = b"x" * (service.MAX_FILE_SIZE + 1)
    upload = UploadFile(
        filename="big.bin",
        file=io.BytesIO(big_bytes),
        headers={"content-type": "application/octet-stream"},
    )
    message = type("Msg", (), {"attachments": []})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service._save_message_attachments([upload], message))
    assert exc.value.status_code == 413
    assert exc.value.detail == "File is too large"


def test_media_processing_noop_for_unknown_extension():
    """Test case for test media processing noop for unknown extension."""
    from app.modules.media.processing import process_media_file

    result = process_media_file("file.unknown")
    assert result == ""


def test_query_helpers_cursor_paginate(session):
    """Test case for test query helpers cursor paginate."""
    u1 = models.User(email="c1@example.com", hashed_password="x")
    u2 = models.User(email="c2@example.com", hashed_password="x")
    session.add_all([u1, u2])
    session.commit()
    query = session.query(models.User).filter(
        models.User.email.in_(["c1@example.com", "c2@example.com"])
    )
    page = cursor_paginate(query, limit=1)
    assert page["count"] == 1
    assert page["next_cursor"]
    page2 = cursor_paginate(query, cursor=page["next_cursor"], limit=1)
    assert page2["count"] == 1
    paginated = paginate_query(query, skip=-5, limit=500)
    assert len(paginated.all()) <= 2


def test_health_smoke_and_readyz_fail_then_ok(monkeypatch, client, session):
    # livez should succeed and include request id header via logging middleware
    """Test case for test health smoke and readyz fail then ok."""
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers

    def failing_db():
        try:

            class Dummy:
                def execute(self, _):
                    raise RuntimeError("db down")

                def close(self):
                    pass

            yield Dummy()
        finally:
            pass

    monkeypatch.setattr(cache_manager, "redis", None)
    app = client.app
    # Preserve the working override to restore it after simulating failure.
    original_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = failing_db
    bad = client.get("/readyz")
    assert bad.status_code == 503
    assert bad.json()["detail"]["database"] == "disconnected"

    # Restore DB override to use the test session again (or the prior override if set)
    if original_override:
        app.dependency_overrides[get_db] = original_override
    else:

        def _test_db():
            try:
                yield session
            finally:
                pass

        app.dependency_overrides[get_db] = _test_db
    good = client.get("/readyz")
    assert good.status_code == 200
