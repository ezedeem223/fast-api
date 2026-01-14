"""Test module for test post service session22."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import models
from app.modules.posts.models import LivingTestimony, PostRelation
from app.services.posts.post_service import PostService
from fastapi import HTTPException


def _user(session, email="u@example.com", verified=True):
    """Helper for  user."""
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_upload_file_post_requires_verified(session, tmp_path):
    """Test case for test upload file post requires verified."""
    service = PostService(session)
    user = _user(session, verified=False)
    fake_upload = SimpleNamespace(file=BytesIO(b"data"), filename="file.txt")

    with pytest.raises(HTTPException) as exc:
        service.upload_file_post(
            file=fake_upload, current_user=user, media_dir=tmp_path / "media"
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "User is not verified."


def test_upload_file_post_creates_record(session, tmp_path):
    """Test case for test upload file post creates record."""
    service = PostService(session)
    user = _user(session)
    fake_upload = SimpleNamespace(file=BytesIO(b"hello"), filename="hello.txt")

    post_out = service.upload_file_post(
        file=fake_upload, current_user=user, media_dir=tmp_path / "media"
    )

    assert post_out.title == "hello.txt"
    assert (tmp_path / "media" / "hello.txt").exists()


def _make_poll(session, owner):
    """Helper for  make poll."""
    post = models.Post(
        owner_id=owner.id,
        title="Poll",
        content="choose",
        is_poll=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    opt1 = models.PollOption(post_id=post.id, option_text="A")
    opt2 = models.PollOption(post_id=post.id, option_text="B")
    session.add_all([opt1, opt2])
    poll = models.Poll(
        post_id=post.id, end_date=datetime.now(timezone.utc) + timedelta(days=1)
    )
    session.add(poll)
    session.commit()
    session.refresh(opt1)
    session.refresh(opt2)
    return post, opt1, opt2, poll


def test_vote_in_poll_success_and_counts(session):
    """Test case for test vote in poll success and counts."""
    service = PostService(session)
    user = _user(session, "poller@example.com")
    post, opt1, _, _ = _make_poll(session, user)

    result = service.vote_in_poll(post_id=post.id, option_id=opt1.id, current_user=user)
    assert result["message"] == "Vote recorded successfully"
    count = (
        session.query(models.PollVote)
        .filter(
            models.PollVote.post_id == post.id, models.PollVote.option_id == opt1.id
        )
        .count()
    )
    assert count == 1


def test_vote_in_poll_invalid_option(session):
    """Test case for test vote in poll invalid option."""
    service = PostService(session)
    user = _user(session, "poller2@example.com")
    post, _, _, _ = _make_poll(session, user)

    with pytest.raises(HTTPException) as exc:
        service.vote_in_poll(post_id=post.id, option_id=9999, current_user=user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Option not found"


def test_vote_in_poll_duplicate_same_option(session):
    """Test case for test vote in poll duplicate same option."""
    service = PostService(session)
    user = _user(session, "poller3@example.com")
    post, opt1, opt2, _ = _make_poll(session, user)
    service.vote_in_poll(post_id=post.id, option_id=opt1.id, current_user=user)

    with pytest.raises(HTTPException) as exc:
        service.vote_in_poll(post_id=post.id, option_id=opt1.id, current_user=user)
    assert exc.value.status_code == 400

    # switching option updates existing vote instead of error
    result = service.vote_in_poll(post_id=post.id, option_id=opt2.id, current_user=user)
    assert result["message"] == "Vote recorded successfully"
    final = (
        session.query(models.PollVote)
        .filter(models.PollVote.post_id == post.id, models.PollVote.user_id == user.id)
        .first()
    )
    assert final.option_id == opt2.id


def test_vote_in_poll_ended(session):
    """Test case for test vote in poll ended."""
    service = PostService(session)
    user = _user(session, "poller4@example.com")
    post = models.Post(
        owner_id=user.id,
        title="Old poll",
        content="done",
        is_poll=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    option = models.PollOption(post_id=post.id, option_text="A")
    session.add(option)
    session.add(
        models.Poll(
            post_id=post.id, end_date=datetime.now(timezone.utc) - timedelta(days=1)
        )
    )
    session.commit()
    session.refresh(option)

    with pytest.raises(HTTPException) as exc:
        service.vote_in_poll(post_id=post.id, option_id=option.id, current_user=user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "This poll has ended"


def test_process_living_memory_creates_relation(session):
    """Test case for test process living memory creates relation."""
    service = PostService(session)
    user = _user(session, "living@example.com")
    old_post = models.Post(
        owner_id=user.id,
        title="Old",
        content="memory lane with shared words",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(old_post)
    session.commit()
    session.refresh(old_post)

    new_post = models.Post(
        owner_id=user.id,
        title="New",
        content="shared words create living memory",
        created_at=datetime.now(timezone.utc),
    )
    session.add(new_post)
    session.commit()
    session.refresh(new_post)

    service._process_living_memory(session, new_post, user.id)

    relation = (
        session.query(PostRelation)
        .filter(
            PostRelation.source_post_id == new_post.id,
            PostRelation.target_post_id == old_post.id,
        )
        .first()
    )
    assert relation is not None
    assert relation.similarity_score >= 0.21


def test_prepare_post_response_sets_living_testimony(session):
    """Test case for test prepare post response sets living testimony."""
    service = PostService(session)
    user = _user(session)
    post = models.Post(
        owner_id=user.id,
        title="Testimony",
        content="content words here",
        created_at=datetime.now(timezone.utc),
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    setattr(post, "owner", user)
    lt = LivingTestimony(post_id=post.id, historical_event="event")
    session.add(lt)
    session.commit()
    session.refresh(post)
    out = service._prepare_post_response(post, owner=user)
    assert out.living_testimony is not None
