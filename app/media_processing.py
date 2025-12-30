"""Compatibility shim for media processing utilities.

Keeps legacy imports (`app.media_processing`) working while the canonical
implementations live under `app.modules.media`.
"""

from app.modules.media import (
    extract_audio_from_video,
    process_media_file,
    scan_file_for_viruses,
    speech_to_text,
)

__all__ = [
    "extract_audio_from_video",
    "process_media_file",
    "scan_file_for_viruses",
    "speech_to_text",
]
