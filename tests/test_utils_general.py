from __future__ import annotations

import base64
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import utils


def test_hash_and_verify_password():
    hashed = utils.hash("secret-password")
    assert hashed != "secret-password"
    assert utils.verify("secret-password", hashed)
    assert not utils.verify("other", hashed)


def test_check_content_against_rules():
    assert utils.check_content_against_rules("hello world", ["forbidden"]) is True
    assert utils.check_content_against_rules("this contains bad", ["bad"]) is False


def test_detect_language_handles_known_text():
    detected = utils.detect_language("Hello world")
    assert isinstance(detected, str)
    assert detected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Visit http://example.com", True),
        ("Broken link http://invalid", False),
    ],
)
def test_validate_urls(text: str, expected: bool):
    assert utils.validate_urls(text) is expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://example.com/video.mp4", False),
    ],
)
def test_is_valid_video_url(url: str, expected: bool):
    assert utils.is_valid_video_url(url) is expected


def test_is_valid_image_url(monkeypatch):
    class DummyResponse:
        headers = {"content-type": "image/png"}

    monkeypatch.setattr("requests.head", lambda url: DummyResponse())
    assert utils.is_valid_image_url("https://example.com/image.png") is True

    class BadResponse:
        headers = {"content-type": "text/html"}

    monkeypatch.setattr("requests.head", lambda url: BadResponse())
    assert utils.is_valid_image_url("https://example.com/image.png") is False


@pytest.mark.parametrize(
    "text, expected_positive",
    [
        ("I absolutely love this platform", True),
        ("This is a terrible experience", False),
    ],
)
def test_analyze_sentiment_keyword_fallback(text: str, expected_positive: bool):
    result = utils.analyze_sentiment(text)
    assert isinstance(result, float)
    if expected_positive:
        assert result > 0
    else:
        assert result <= 0


@pytest.mark.parametrize(
    "text, contains",
    [
        ("This text is totally innocent", False),
        ("This text is shit", True),
    ],
)
def test_check_for_profanity(text: str, contains: bool):
    assert bool(utils.check_for_profanity(text)) is contains


def test_generate_qr_code_returns_base64():
    qr = utils.generate_qr_code("data")
    decoded = base64.b64decode(qr.encode())
    assert decoded.startswith(b"\x89PNG")


def test_generate_and_update_encryption_key():
    original = utils.generate_encryption_key()
    updated = utils.update_encryption_key(original)
    assert original != updated
    assert len(updated) == len(original)


def test_get_client_ip_prefers_forwarded_header():
    request = SimpleNamespace(headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}, client=SimpleNamespace(host="3.3.3.3"))
    assert utils.get_client_ip(request) == "1.1.1.1"


def test_get_client_ip_falls_back_to_client():
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="4.4.4.4"))
    assert utils.get_client_ip(request) == "4.4.4.4"


def test_is_ip_banned_handles_active_and_expired(monkeypatch):
    active_ban = SimpleNamespace(expires_at=datetime.now() + timedelta(minutes=5))
    expired_ban = SimpleNamespace(expires_at=datetime.now() - timedelta(minutes=5))

    active_query = MagicMock()
    active_query.filter.return_value.first.return_value = active_ban
    expired_query = MagicMock()
    expired_query.filter.return_value.first.return_value = expired_ban

    db = MagicMock()
    db.query.side_effect = [active_query, expired_query]

    assert utils.is_ip_banned(db, "5.5.5.5") is True
    assert utils.is_ip_banned(db, "5.5.5.5") is False
    db.delete.assert_called_once_with(expired_ban)
    db.commit.assert_called()


def test_detect_ip_evasion():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.distinct.return_value.all.return_value = [("10.0.0.1",)]
    assert utils.detect_ip_evasion(db, 1, "10.0.0.2") is False

    query.filter.return_value.distinct.return_value.all.return_value = [
        ("10.0.0.1",),
        ("8.8.8.8",),
    ]
    assert utils.detect_ip_evasion(db, 1, "8.8.4.4") is True
