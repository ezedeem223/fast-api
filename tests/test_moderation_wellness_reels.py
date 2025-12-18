from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import models, schemas
from app.modules.moderation import service as moderation_service
from app.services.moderation.banned_word_service import BannedWordService
from app.modules.wellness.service import WellnessService
from app.services.reels.service import ReelService


def _user(session, email="u@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_moderation_unblock_and_clean_expired(session):
    blocker = _user(session, "blocker@example.com")
    blocked = _user(session, "blocked@example.com")
    active_block = models.Block(
        blocker_id=blocker.id,
        blocked_id=blocked.id,
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
        block_type=models.BlockType.FULL,
    )
    expired_block = models.Block(
        blocker_id=blocker.id,
        blocked_id=blocked.id,
        ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        block_type=models.BlockType.FULL,
    )
    session.add_all([active_block, expired_block])
    session.commit()

    # Unblock updates ends_at for active
    updated = moderation_service.unblock_user(session, blocker.id, blocked.id)
    assert updated == 1
    session.refresh(active_block)
    assert active_block.ends_at is not None

    # Clean removes expired
    deleted = moderation_service.clean_expired_blocks(session)
    assert deleted >= 1
    remaining = session.query(models.Block).count()
    assert remaining == 0  # all cleaned after unblock ends block


def test_banned_word_stats_and_cleanup(session):
    admin = _user(session, "admin@example.com")
    svc = BannedWordService(session)

    word = svc.add_word(
        payload=schemas.BannedWordCreate(word="spam", severity="warn"),
        current_user=admin,
    )
    assert word.id

    removed = svc.remove_word(word_id=word.id, current_user=admin)
    assert "removed" in removed["message"]


def test_wellness_bounds_and_modes(session):
    user = _user(session)

    # Bounds: negative rejected
    with pytest.raises(ValueError):
        WellnessService.update_usage_metrics(session, user.id, -5)

    metrics = WellnessService.update_usage_metrics(session, user.id, 45)
    assert metrics.usage_pattern == models.UsagePattern.LIGHT

    # Mode transitions
    dnd = WellnessService.enable_do_not_disturb(session, user.id, duration_minutes=10)
    assert dnd.do_not_disturb is True and dnd.do_not_disturb_until > datetime.now(timezone.utc)

    mh = WellnessService.enable_mental_health_mode(session, user.id, duration_minutes=5)
    assert mh.mental_health_mode is True and mh.mental_health_mode_until > datetime.now(timezone.utc)

    # Alert creation
    alert = WellnessService.create_wellness_alert(
        session, user.id, alert_type="usage", severity="high", message="too much"
    )
    assert alert.id

    # Missing session logs error and returns None
    assert WellnessService.end_wellness_session(session, session_id=9999) is None


def _community_member(session, user):
    community = models.Community(name="c", description="d", owner_id=user.id)
    membership = models.CommunityMember(
        community=community, user=user, role=models.CommunityRole.OWNER
    )
    session.add_all([community, membership])
    session.commit()
    session.refresh(community)
    return community


def test_reels_cleanup_and_constraints(session):
    owner = _user(session)
    community = _community_member(session, owner)
    svc = ReelService(session)

    # Create active reel with membership
    reel = svc.create_reel(
        payload=schemas.ReelCreate(
            title="r1", video_url="http://v", description="", community_id=community.id, expires_in_hours=1
        ),
        current_user=owner,
    )
    # Expire it manually and cleanup
    reel.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    cleaned = svc.cleanup_expired_reels()
    assert cleaned == 1
    session.refresh(reel)
    assert reel.is_active is False

    # Non-member publish constraint
    other = _user(session, "other@example.com")
    with pytest.raises(HTTPException):
        svc.create_reel(
            payload=schemas.ReelCreate(
                title="r2", video_url="http://v2", description="", community_id=community.id, expires_in_hours=1
            ),
            current_user=other,
        )

    # record_view on expired raises but doesn't crash service
    with pytest.raises(HTTPException):
        svc.record_view(reel_id=reel.id)
