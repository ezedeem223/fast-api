"""FFmpeg/speech helpers for media processing."""

from __future__ import annotations

import logging
from pathlib import Path

import ffmpeg

logger = logging.getLogger(__name__)


def extract_audio_from_video(video_path: str) -> str:
    output_path = Path(video_path).with_suffix(".wav")
    try:
        stream = ffmpeg.input(video_path)
        stream = ffmpeg.output(stream, str(output_path))
        ffmpeg.run(stream, overwrite_output=True)
        return str(output_path)
    except Exception as exc:  # pragma: no cover - ffmpeg errors vary
        logger.error("Error extracting audio from video %s: %s", video_path, exc)
        raise


def speech_to_text(audio_path: str) -> str:
    import speech_recognition as sr  # Deferred import to avoid module-wide warnings

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="ar-AR")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as exc:
        logger.error("Speech recognition API error: %s", exc)
        return ""


def process_media_file(file_path: str) -> str:
    file_path_lower = file_path.lower()
    if file_path_lower.endswith((".mp4", ".avi", ".mov")):
        audio_path = extract_audio_from_video(file_path)
    elif file_path_lower.endswith((".mp3", ".wav", ".ogg")):
        audio_path = file_path
    else:
        return ""
    return speech_to_text(audio_path)


def scan_file_for_viruses(file_path: str) -> bool:
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", category=DeprecationWarning, module="pkg_resources"
        )
        import clamd  # Deferred import to avoid module-level warnings

    try:
        cd = clamd.ClamdNetworkSocket()
        result = cd.scan(file_path)
        if result and file_path in result and result[file_path][0] == "FOUND":
            return False
        return True
    except Exception as exc:
        logger.error("Error scanning file for viruses: %s", exc)
        return True
