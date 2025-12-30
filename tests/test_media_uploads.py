import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from app import models
from app.routers import post as post_router
from app.services.posts.post_service import PostService
from fastapi import BackgroundTasks


def _fake_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers={"content-type": content_type},
    )


def _fake_user(test_user) -> SimpleNamespace:
    return SimpleNamespace(
        id=test_user["id"],
        is_verified=True,
        email=test_user["email"],
        username="tester",
        privacy_level="public",
    )


def test_upload_file_creates_post(session, test_user):
    upload = _fake_upload_file("doc.pdf", b"fake-pdf-content", "application/pdf")
    service = PostService(session)
    result = service.upload_file_post(
        file=upload,
        current_user=_fake_user(test_user),
        media_dir=post_router.MEDIA_DIR,
    )
    post = session.query(models.Post).filter_by(id=result.id).first()
    assert post is not None
    assert post.content
    assert Path(post.content).exists()


def test_upload_short_video(session, test_user):
    upload = _fake_upload_file("clip.mp4", b"0" * 1024, "video/mp4")
    service = PostService(session)
    post_obj = service.create_short_video(
        background_tasks=None,
        file=upload,
        current_user=_fake_user(test_user),
        media_dir=post_router.MEDIA_DIR,
        queue_email_fn=lambda *args, **kwargs: None,
    )
    post = session.query(models.Post).filter_by(id=post_obj.id).first()
    assert post is not None
    assert post.is_short_video
    assert post.content and Path(post.content).exists()


@pytest.mark.asyncio
async def test_upload_audio_post(session, tmp_path: Path, test_user):
    upload = _fake_upload_file("sound.mp3", b"fakedata", "audio/mpeg")
    service = PostService(session)

    async def save_audio_fn(file: UploadFile) -> str:
        target_dir = tmp_path / "audio"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / file.filename
        content = await file.read()
        with open(file_path, "wb") as fh:
            fh.write(content)
        return str(file_path)

    def analyze_content_fn(text: str) -> dict:
        return {
            "sentiment": {"sentiment": "positive", "score": 0.9},
            "suggestion": "All good",
        }

    new_post = await service.create_audio_post(
        background_tasks=BackgroundTasks(),
        title="Audio Title",
        description="No mentions here",
        audio_file=upload,
        current_user=_fake_user(test_user),
        save_audio_fn=save_audio_fn,
        analyze_content_fn=analyze_content_fn,
        queue_email_fn=lambda *args, **kwargs: None,
        mention_notifier_fn=lambda *args, **kwargs: None,
    )
    post = session.query(models.Post).filter_by(id=new_post.id).first()
    assert post is not None
    assert post.audio_url is not None
    assert post.is_audio_post
    assert Path(post.audio_url).exists()
