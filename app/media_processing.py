import ffmpeg
import speech_recognition as sr
from pathlib import Path


def extract_audio_from_video(video_path):
    output_path = Path(video_path).with_suffix(".wav")
    stream = ffmpeg.input(video_path)
    stream = ffmpeg.output(stream, str(output_path))
    ffmpeg.run(stream, overwrite_output=True)
    return str(output_path)


def speech_to_text(audio_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio, language="ar-AR")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return ""


def process_media_file(file_path):
    if file_path.endswith((".mp4", ".avi", ".mov")):
        audio_path = extract_audio_from_video(file_path)
    elif file_path.endswith((".mp3", ".wav", ".ogg")):
        audio_path = file_path
    else:
        return ""

    return speech_to_text(audio_path)
