import asyncio
import io
import os
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import analytics, models
from app.ai_chat import amenhotep as amenhotep_module
from app.core.cache.redis_cache import cache_manager
from app.core.database import get_db
from app.core.database.query_helpers import cursor_paginate, paginate_query
from app.modules.community.models import SearchStatistics
from app.services.messaging import MessageService


def test_analytics_lazy_pipeline_cached(monkeypatch):
    created = object()

    class DummyPipeline:
        def __call__(self, text):
            return [{"label": "POSITIVE", "score": 0.9}]

    monkeypatch.setattr(analytics, "_sentiment_pipeline", None)
    monkeypatch.setattr(analytics, "pipeline", lambda *_, **__: DummyPipeline())
    monkeypatch.setattr(analytics, "AutoTokenizer", type("Tok", (), {"from_pretrained": lambda *_: None}))
    monkeypatch.setattr(analytics, "AutoModelForSequenceClassification", type("Mod", (), {"from_pretrained": lambda *_: created}))

    first = analytics._get_sentiment_pipeline()
    second = analytics._get_sentiment_pipeline()
    assert first is second


def test_suggest_improvements_short_text():
    suggestion = analytics.suggest_improvements("too short", {"sentiment": "POSITIVE", "score": 0.1})
    assert "short" in suggestion.lower()


def test_suggest_improvements_negative():
    suggestion = analytics.suggest_improvements(
        "bad text", {"sentiment": "NEGATIVE", "score": 0.95}
    )
    assert "rephrasing" in suggestion.lower() or "rephrase" in suggestion.lower()


def test_clean_old_statistics(session):
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
    monkeypatch.setattr(os.path, "exists", lambda *_: False)
    kb = amenhotep_module.AmenhotepAI._load_knowledge_base(None)
    assert isinstance(kb, dict)
    assert kb


def test_amenhotep_expand_knowledge_base_writes(monkeypatch, tmp_path):
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


def test_media_processing_noop_for_unknown_extension():
    from app.modules.media.processing import process_media_file

    result = process_media_file("file.unknown")
    assert result == ""


def test_query_helpers_cursor_paginate(session):
    u1 = models.User(email="c1@example.com", hashed_password="x")
    u2 = models.User(email="c2@example.com", hashed_password="x")
    session.add_all([u1, u2])
    session.commit()
    query = session.query(models.User)
    page = cursor_paginate(query, limit=1)
    assert page["count"] == 1
    assert page["next_cursor"]
    page2 = cursor_paginate(query, cursor=page["next_cursor"], limit=1)
    assert page2["count"] == 1
    paginated = paginate_query(query, skip=-5, limit=500)
    assert len(paginated.all()) <= 2


def test_health_smoke_and_readyz_fail_then_ok(monkeypatch, client, session):
    # livez should succeed and include request id header via logging middleware
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers

    original_get_db = get_db

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
    app.dependency_overrides[get_db] = failing_db
    bad = client.get("/readyz")
    assert bad.status_code == 503
    assert bad.json()["detail"]["database"] == "disconnected"

    app.dependency_overrides.pop(get_db, None)
    good = client.get("/readyz")
    assert good.status_code == 200
