from app import media_processing


def test_extract_audio_from_video(monkeypatch, tmp_path):
    calls = {}

    def fake_input(path):
        calls["input"] = path
        return "stream"

    def fake_output(stream, output_path):
        calls["output"] = output_path
        return "final"

    def fake_run(stream, overwrite_output=True):
        calls["run"] = (stream, overwrite_output)
        return None

    monkeypatch.setattr(media_processing.ffmpeg, "input", fake_input)
    monkeypatch.setattr(media_processing.ffmpeg, "output", fake_output)
    monkeypatch.setattr(media_processing.ffmpeg, "run", fake_run)

    video = tmp_path / "clip.mp4"
    video.write_text("data")

    audio_path = media_processing.extract_audio_from_video(str(video))

    assert audio_path.endswith(".wav")
    assert calls["input"] == str(video)
    assert calls["run"] == ("final", True)


def test_speech_to_text_happy_path(monkeypatch):
    class DummyRecognizer:
        def __init__(self):
            self.recorded_source = None

        def record(self, source):
            self.recorded_source = source
            return "audio"

        def recognize_google(self, audio, language="ar-AR"):
            assert audio == "audio"
            assert language == "ar-AR"
            return "transcript"

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return "source"

        def __exit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr(media_processing.sr, "Recognizer", DummyRecognizer)
    monkeypatch.setattr(media_processing.sr, "AudioFile", DummyAudioFile)

    result = media_processing.speech_to_text("/tmp/sample.wav")

    assert result == "transcript"


def test_process_media_file_routes_video(monkeypatch):
    monkeypatch.setattr(
        media_processing,
        "extract_audio_from_video",
        lambda path: "converted.wav",
    )
    monkeypatch.setattr(media_processing, "speech_to_text", lambda path: "text")

    assert media_processing.process_media_file("movie.MP4") == "text"
    assert media_processing.process_media_file("note.mp3") == "text"
    assert media_processing.process_media_file("image.png") == ""


def test_scan_file_for_viruses(monkeypatch):
    class CleanScanner:
        def scan(self, file_path):
            return {file_path: ("OK", None)}

    class DirtyScanner:
        def scan(self, file_path):
            return {file_path: ("FOUND", "virus")}

    monkeypatch.setattr(media_processing.clamd, "ClamdNetworkSocket", CleanScanner)
    assert media_processing.scan_file_for_viruses("file.txt") is True

    monkeypatch.setattr(media_processing.clamd, "ClamdNetworkSocket", DirtyScanner)
    assert media_processing.scan_file_for_viruses("file.txt") is False
