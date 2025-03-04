import ffmpeg
import speech_recognition as sr
from pathlib import Path
import clamd
import logging

logger = logging.getLogger(__name__)


def extract_audio_from_video(video_path: str) -> str:
    output_path = Path(video_path).with_suffix(".wav")
    try:
        stream = ffmpeg.input(video_path)
        stream = ffmpeg.output(stream, str(output_path))
        ffmpeg.run(stream, overwrite_output=True)
        return str(output_path)
    except Exception as e:
        logger.error(f"Error extracting audio from video {video_path}: {e}")
        raise


def speech_to_text(audio_path: str) -> str:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="ar-AR")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        logger.error(f"Speech recognition API error: {e}")
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
    try:
        cd = clamd.ClamdNetworkSocket()
        result = cd.scan(file_path)
        if result and file_path in result and result[file_path][0] == "FOUND":
            return False
        return True
    except Exception as e:
        logger.error(f"Error scanning file for viruses: {e}")
        return True
