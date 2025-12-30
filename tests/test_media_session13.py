import sys

import pytest

import app.modules.media.processing as media_proc


def test_extract_audio_from_video_success(monkeypatch, tmp_path):
    calls = {}

    class DummyStream:
        pass

    def fake_input(path):
        calls["input"] = path
        return DummyStream()

    def fake_output(stream, out_path):
        calls["output"] = (stream, out_path)
        return "output-stream"

    def fake_run(stream, overwrite_output=None):
        calls["run"] = (stream, overwrite_output)

    monkeypatch.setattr(media_proc, "ffmpeg", type("FF", (), {"input": fake_input, "output": fake_output, "run": fake_run}))

    src = tmp_path / "video.mp4"
    src.write_bytes(b"data")
    out = media_proc.extract_audio_from_video(str(src))
    assert out == str(src.with_suffix(".wav"))
    assert calls["input"] == str(src)
    assert calls["output"][1] == str(src.with_suffix(".wav"))
    assert calls["run"] == ("output-stream", True)


def test_extract_audio_from_video_raises_on_error(monkeypatch):
    def boom(path):
        raise RuntimeError("ffmpeg fail")

    monkeypatch.setattr(media_proc, "ffmpeg", type("FF", (), {"input": boom}))

    with pytest.raises(RuntimeError):
        media_proc.extract_audio_from_video("bad.mp4")


def test_speech_to_text_unknown_value(monkeypatch):
    class DummyRecognizer:
        def record(self, source):
            return "audio"

        def recognize_google(self, audio, language=None):
            raise DummySR.UnknownValueError()

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return "source"

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class DummySR:
        UnknownValueError = type("UnknownValueError", (Exception,), {})
        RequestError = type("RequestError", (Exception,), {})

        def AudioFile(self, path):
            return DummyAudioFile(path)

        def Recognizer(self):
            return DummyRecognizer()

    monkeypatch.setitem(sys.modules, "speech_recognition", DummySR())
    assert media_proc.speech_to_text("audio.wav") == ""


def test_speech_to_text_request_error(monkeypatch):
    class DummyRecognizer:
        def record(self, source):
            return "audio"

        def recognize_google(self, audio, language=None):
            raise DummySR.RequestError("api down")

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return "source"

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class DummySR:
        UnknownValueError = type("UnknownValueError", (Exception,), {})
        RequestError = type("RequestError", (Exception,), {})

        def AudioFile(self, path):
            return DummyAudioFile(path)

        def Recognizer(self):
            return DummyRecognizer()

    monkeypatch.setitem(sys.modules, "speech_recognition", DummySR())
    assert media_proc.speech_to_text("audio.wav") == ""


def test_scan_file_for_viruses_found(monkeypatch, tmp_path):
    scanned = []

    class DummyClamd:
        def __init__(self):
            scanned.append("init")

        def scan(self, path):
            scanned.append(path)
            return {path: ("FOUND", "EICAR")}

    dummy_mod = type("clamd", (), {"ClamdNetworkSocket": DummyClamd})
    monkeypatch.setitem(sys.modules, "clamd", dummy_mod)
    file_path = str(tmp_path / "file.bin")
    assert media_proc.scan_file_for_viruses(file_path) is False
    assert scanned[0] == "init"


def test_scan_file_for_viruses_clean(monkeypatch, tmp_path):
    class DummyClamd:
        def scan(self, path):
            return {path: ("OK", None)}

    dummy_mod = type("clamd", (), {"ClamdNetworkSocket": DummyClamd})
    monkeypatch.setitem(sys.modules, "clamd", dummy_mod)
    assert media_proc.scan_file_for_viruses(str(tmp_path / "clean.bin")) is True


def test_scan_file_for_viruses_exception(monkeypatch, tmp_path):
    class DummyClamd:
        def scan(self, path):
            raise RuntimeError("socket error")

    dummy_mod = type("clamd", (), {"ClamdNetworkSocket": DummyClamd})
    monkeypatch.setitem(sys.modules, "clamd", dummy_mod)
    assert media_proc.scan_file_for_viruses(str(tmp_path / "err.bin")) is True
