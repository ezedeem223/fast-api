import base64
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from fastapi import HTTPException

import app.firebase_config as firebase_config
import app.link_preview as link_preview
from app.modules.media import processing
from app.modules.utils import files as file_utils
from app.modules.utils import security as security_utils


def test_firebase_push_and_topic_fallback(monkeypatch):
    """Exercise happy/error paths without hitting real Firebase."""
    monkeypatch.setattr(firebase_config.messaging, "Message", lambda **kwargs: kwargs)
    monkeypatch.setattr(firebase_config.messaging, "Notification", lambda **kwargs: kwargs)
    # send_push_notification should swallow errors and return None
    monkeypatch.setattr(
        firebase_config.messaging,
        "send",
        lambda message: (_ for _ in ()).throw(RuntimeError("send failure")),
    )
    assert firebase_config.send_push_notification("tok", "title", "body") is None

    # subscribe succeeds, unsubscribe failure is handled
    monkeypatch.setattr(
        firebase_config.messaging,
        "subscribe_to_topic",
        lambda tokens, topic: {"tokens": tokens, "topic": topic},
    )
    assert firebase_config.subscribe_to_topic(["a", "b"], "news")["topic"] == "news"
    monkeypatch.setattr(
        firebase_config.messaging,
        "unsubscribe_from_topic",
        lambda tokens, topic: (_ for _ in ()).throw(RuntimeError("bad request")),
    )
    assert firebase_config.unsubscribe_from_topic(["a"], "news") is None


def test_extract_link_preview_network_error(monkeypatch):
    """Network failure should simply return None."""
    monkeypatch.setattr(link_preview.validators, "url", lambda u: True)
    monkeypatch.setattr(
        link_preview.requests,
        "get",
        lambda url, timeout=5: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert link_preview.extract_link_preview("http://example.com") is None


def test_process_media_file_branches(monkeypatch):
    """Video path should be converted then transcribed; unsupported types return empty."""
    calls = {}
    def fake_extract(path):
        calls["video"] = path
        return "audio.wav"

    monkeypatch.setattr(processing, "extract_audio_from_video", fake_extract)
    monkeypatch.setattr(processing, "speech_to_text", lambda path: f"txt:{path}")
    assert processing.process_media_file("movie.MP4") == "txt:audio.wav"
    assert calls["video"] == "movie.MP4"

    # Unsupported extension yields empty string
    assert processing.process_media_file("document.pdf") == ""


def test_speech_to_text_error_branches(monkeypatch):
    """Handle speech recognition unknown/request errors gracefully."""
    failure_mode = {"mode": "unknown"}
    UnknownValueError = type("UnknownValueError", (Exception,), {})
    RequestError = type("RequestError", (Exception,), {})

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyRecognizer:
        def record(self, source):
            return b"audio-bytes"

        def recognize_google(self, audio, language="ar-AR"):
            if failure_mode["mode"] == "unknown":
                raise UnknownValueError()
            if failure_mode["mode"] == "request":
                raise RequestError("api down")
            return "recognized speech"

    dummy_sr = SimpleNamespace(
        Recognizer=lambda: DummyRecognizer(),
        AudioFile=DummyAudioFile,
        UnknownValueError=UnknownValueError,
        RequestError=RequestError,
    )
    monkeypatch.setitem(sys.modules, "speech_recognition", dummy_sr)
    assert processing.speech_to_text("file.wav") == ""
    failure_mode["mode"] = "request"
    assert processing.speech_to_text("file.wav") == ""
    failure_mode["mode"] = None
    assert processing.speech_to_text("file.wav") == "recognized speech"


def test_generate_qr_code_and_save_upload(tmp_path):
    """QR code is valid PNG."""
    qr_data = file_utils.generate_qr_code("hello")
    qr_bytes = base64.b64decode(qr_data)
    assert qr_bytes.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_save_upload_file(tmp_path):
    """Uploaded file should be written to disk in the target folder."""
    upload = UploadFile(filename="sample.txt", file=BytesIO(b"content"))
    saved_path = await file_utils.save_upload_file(upload, folder=tmp_path)
    saved_path = Path(saved_path)
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"content"


@pytest.mark.asyncio
async def test_admin_required_allows_admin(monkeypatch):
    """admin_required should allow admins and block non-admins."""
    async def fake_admin():
        return SimpleNamespace(is_admin=True)

    async def fake_user():
        return SimpleNamespace(is_admin=False)

    @security_utils.admin_required
    async def protected():
        return "ok"

    monkeypatch.setattr("app.oauth2.get_current_user", fake_admin)
    assert await protected() == "ok"

    monkeypatch.setattr("app.oauth2.get_current_user", fake_user)
    with pytest.raises(HTTPException):
        await protected()


@pytest.mark.asyncio
async def test_handle_exceptions_wraps_errors():
    """handle_exceptions converts generic errors to HTTPException 500."""

    @security_utils.handle_exceptions
    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc_info:
        await failing()

    assert exc_info.value.status_code == 500
    assert "boom" in exc_info.value.detail
