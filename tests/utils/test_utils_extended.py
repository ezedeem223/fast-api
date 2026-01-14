"""Test module for test utils extended."""
from types import SimpleNamespace

import pytest

from app.modules.utils import analytics, common, network, translation

# ----------------------- common.get_user_display_name ----------------------- #


@pytest.mark.parametrize(
    "user_attrs,expected",
    [
        ({"username": "hero", "email": "hero@example.com"}, "hero"),
        ({"account_username": "legacy", "email": "legacy@example.com"}, "legacy"),
        ({"email": "email@example.com"}, "email@example.com"),
        ({"username": "", "account_username": "acct", "email": "c@x.com"}, "acct"),
        (
            {"username": None, "account_username": None, "email": "fallback@x.com"},
            "fallback@x.com",
        ),
        ({"username": "Name", "account_username": "acct", "email": "mail"}, "Name"),
        ({"username": "", "account_username": "", "email": "z"}, "z"),
        (
            {"username": None, "account_username": "   user   ", "email": "mail"},
            "   user   ",
        ),
        ({"username": "UPPER", "account_username": "lower", "email": "mail"}, "UPPER"),
        (
            {
                "username": None,
                "account_username": None,
                "email": "duplicate@example.com",
            },
            "duplicate@example.com",
        ),
    ],
)
def test_get_user_display_name_variations(user_attrs, expected):
    """Test case for test get user display name variations."""
    user = SimpleNamespace(**user_attrs)
    assert common.get_user_display_name(user) == expected


# ----------------------- network.get_client_ip ----------------------------- #


class DummyRequest:
    """Test class for DummyRequest."""
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = SimpleNamespace(host=host)


@pytest.mark.parametrize(
    "headers,host,expected",
    [
        ({"X-Forwarded-For": "1.1.1.1"}, "10.0.0.1", "1.1.1.1"),
        ({"X-Forwarded-For": "2.2.2.2, 3.3.3.3"}, "10.0.0.1", "2.2.2.2"),
        ({}, "203.0.113.4", "203.0.113.4"),
        ({"Other": "value"}, "192.0.2.10", "192.0.2.10"),
        ({"X-Forwarded-For": " 4.4.4.4 , 5.5.5.5 "}, "0.0.0.0", "4.4.4.4"),
        ({"X-Forwarded-For": ""}, "198.51.100.20", "198.51.100.20"),
    ],
)
def test_get_client_ip_sources(headers, host, expected):
    """Test case for test get client ip sources."""
    request = DummyRequest(headers=headers, host=host)
    assert network.get_client_ip(request) == expected


# ----------------------- translation.cached_translate_text ----------------- #


@pytest.mark.asyncio
async def test_cached_translate_text_hits_cache(monkeypatch):
    """Test case for test cached translate text hits cache."""
    calls = {"count": 0}

    async def fake_translate(text, source, target):
        calls["count"] += 1
        return f"{text}-{target}"

    translation.translation_cache.clear()
    monkeypatch.setattr(translation, "translate_text", fake_translate, raising=False)

    result1 = await translation.cached_translate_text("hello", "en", "fr")
    result2 = await translation.cached_translate_text("hello", "en", "fr")

    assert result1 == "hello-fr"
    assert result2 == "hello-fr"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_cached_translate_text_different_keys(monkeypatch):
    """Test case for test cached translate text different keys."""
    translation.translation_cache.clear()

    async def fake_translate(text, source, target):
        return f"{text}:{source}->{target}"

    monkeypatch.setattr(translation, "translate_text", fake_translate, raising=False)

    r1 = await translation.cached_translate_text("hi", "en", "es")
    r2 = await translation.cached_translate_text("hi", "en", "de")
    assert r1 == "hi:en->es"
    assert r2 == "hi:en->de"


@pytest.mark.asyncio
async def test_cached_translate_text_cache_invalidation(monkeypatch):
    """Test case for test cached translate text cache invalidation."""
    translation.translation_cache.clear()

    async def fake_translate(text, source, target):
        return f"{text}:{target}"

    monkeypatch.setattr(translation, "translate_text", fake_translate, raising=False)
    await translation.cached_translate_text("ping", "en", "es")
    translation.translation_cache.clear()
    result = await translation.cached_translate_text("ping", "en", "es")
    assert result == "ping:es"


# ----------------------- translation.get_translated_content ---------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_attrs,source_lang,content,translated,should_translate",
    [
        (
            {"preferred_language": "fr", "auto_translate": True},
            "en",
            "Hello",
            "Bonjour",
            True,
        ),
        (
            {"preferred_language": "en", "auto_translate": True},
            "en",
            "Same",
            "Same",
            False,
        ),
        (
            {"preferred_language": None, "auto_translate": True},
            "en",
            "Text",
            "Text",
            False,
        ),
        (
            {"preferred_language": "de", "auto_translate": False},
            "en",
            "Skip",
            "Skip",
            False,
        ),
        (
            {"preferred_language": "es", "auto_translate": True},
            "es",
            "Hola",
            "Hola",
            False,
        ),
        ({"preferred_language": "it", "auto_translate": True}, "en", "", "", False),
        (
            {"preferred_language": "ar", "auto_translate": True},
            "en",
            "مرحبا",
            "مرحباً",
            True,
        ),
        (
            {"preferred_language": "ru", "auto_translate": True},
            "en",
            "Error",
            "Error",
            "not_impl",
        ),
        (
            {"preferred_language": "ja", "auto_translate": True},
            "en",
            "Oops",
            "Oops",
            "exception",
        ),
        (
            {"preferred_language": "pt", "auto_translate": True},
            "en",
            "Content",
            "Conteúdo",
            True,
        ),
    ],
)
async def test_get_translated_content(
    monkeypatch, user_attrs, source_lang, content, translated, should_translate
):
    """Test case for test get translated content."""
    user = SimpleNamespace(**user_attrs)
    translation.translation_cache.clear()

    # Arrange: stub translation behavior based on the expected branch.
    async def fake_translate(text, src, tgt):
        if should_translate == "not_impl":
            raise NotImplementedError
        if should_translate == "exception":
            raise RuntimeError("fail")
        return translated

    called = {"count": 0}

    async def fake_cached(text, src, tgt):
        called["count"] += 1
        return await fake_translate(text, src, tgt)

    monkeypatch.setattr(
        translation, "cached_translate_text", fake_cached, raising=False
    )
    monkeypatch.setattr(
        translation,
        "logger",
        SimpleNamespace(exception=lambda *args, **kwargs: None),
        raising=False,
    )

    # Act: request translated content.
    result = await translation.get_translated_content(content, user, source_lang)

    # Assert: translation is applied only when required.
    if should_translate is True:
        assert result == translated
        assert called["count"] == 1
    elif should_translate in ("not_impl", "exception"):
        assert result == content
    else:
        assert result == content
        assert called["count"] == 0


# ----------------------- analytics.CallQualityBuffer ----------------------- #


@pytest.mark.parametrize(
    "scores,expected",
    [
        ([], 100.0),
        ([80], 80),
        ([90, 70], 80),
        ([50, 60, 70], 60),
        ([100] * 10, 100),
        ([10, 20, 30, 40, 50], 30),
        ([100, 50, 0], 50),
    ],
)
def test_call_quality_buffer_average(scores, expected):
    """Test case for test call quality buffer average."""
    buffer = analytics.CallQualityBuffer(window_size=5)
    for score in scores:
        buffer.add_score(score)
    assert pytest.approx(buffer.get_average_score(), rel=1e-3) == expected


# ----------------------- analytics.check_call_quality ---------------------- #


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"packet_loss": 0, "latency": 0, "jitter": 0}, 100),
        ({"packet_loss": 5, "latency": 50, "jitter": 10}, 100 - (10 + 5 + 10)),
        ({"packet_loss": 1, "latency": 20, "jitter": 5}, 100 - (2 + 2 + 5)),
        ({"packet_loss": 10, "latency": 100, "jitter": 20}, 100 - (20 + 10 + 20)),
        ({}, 100),
        ({"packet_loss": 0, "latency": 100, "jitter": 0}, 90),
        ({"packet_loss": 15, "latency": 0, "jitter": 0}, 70),
    ],
)
def test_check_call_quality(data, expected):
    """Test case for test check call quality."""
    analytics.quality_buffers.clear()
    score = analytics.check_call_quality(data, call_id="abc")
    assert pytest.approx(score, rel=1e-3) == expected


# ----------------------- analytics.should_adjust_video_quality ------------- #


@pytest.mark.parametrize(
    "scores,expected",
    [
        ([100, 90], False),
        ([30, 40], True),
        ([50, 60], False),
        ([10, 20, 30], True),
        ([], False),
    ],
)
def test_should_adjust_video_quality(scores, expected):
    """Test case for test should adjust video quality."""
    analytics.quality_buffers.clear()
    buffer = analytics.CallQualityBuffer(window_size=5)
    for score in scores:
        buffer.add_score(score)
    analytics.quality_buffers["call"] = buffer
    assert analytics.should_adjust_video_quality("call") is expected


# ----------------------- analytics.get_recommended_video_quality ----------- #


@pytest.mark.parametrize(
    "scores,expected",
    [
        ([80, 90], "high"),
        ([50, 50], "medium"),
        ([10, 15], "low"),
        ([], "high"),
        ([35], "medium"),
        ([25], "low"),
    ],
)
def test_get_recommended_video_quality(scores, expected):
    """Test case for test get recommended video quality."""
    analytics.quality_buffers.clear()
    buffer = analytics.CallQualityBuffer(window_size=5)
    for score in scores:
        buffer.add_score(score)
    if scores:
        analytics.quality_buffers["call"] = buffer
    assert analytics.get_recommended_video_quality("call") == expected


# ----------------------- analytics.clean_old_quality_buffers --------------- #


def test_clean_old_quality_buffers(monkeypatch):
    """Test case for test clean old quality buffers."""
    analytics.quality_buffers.clear()
    buffer_recent = analytics.CallQualityBuffer()
    buffer_old = analytics.CallQualityBuffer()

    analytics.quality_buffers["recent"] = buffer_recent
    analytics.quality_buffers["old"] = buffer_old

    monkeypatch.setattr(buffer_recent, "last_update_time", 1000, raising=False)
    monkeypatch.setattr(buffer_old, "last_update_time", 0, raising=False)

    monkeypatch.setattr(analytics.time, "time", lambda: 1000 + 100, raising=False)

    analytics.clean_old_quality_buffers()
    assert "old" not in analytics.quality_buffers
    assert "recent" in analytics.quality_buffers
