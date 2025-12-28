import re
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.content_filter import check_content, filter_content
from app.modules.fact_checking.models import FactCheckStatus
from app.modules.fact_checking.service import FactCheckingService
from app.modules.utils.moderation import log_admin_action
from app.services.reels import ReelService


def test_banned_word_regex_matching(session, test_user):
    bw = models.BannedWord(word=r"foo\d+", severity="ban", is_regex=True, created_by=test_user["id"])
    session.add(bw)
    session.commit()

    warnings, bans = check_content(session, "foo123 is bad")
    assert bans == [bw.word]

    filtered = filter_content(session, "foo123 is bad")
    assert re.search(r"\*", filtered)


def test_admin_audit_log_persisted(session, test_user):
    initial = session.query(models.AuditLog).count()
    log_admin_action(session, admin_id=test_user["id"], action="manual_test", metadata={"foo": "bar"})
    after = session.query(models.AuditLog).count()
    assert after == initial + 1


def test_reel_cleanup_archives(session, test_user):
    community = models.Community(
        name="test-community",
        owner_id=test_user["id"],
        description="desc",
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    reel = models.Reel(
        title="old",
        video_url="http://example.com/reel.mp4",
        description="expired",
        owner_id=test_user["id"],
        community_id=community.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        is_active=True,
        view_count=3,
    )
    session.add(reel)
    session.commit()
    session.refresh(reel)

    svc = ReelService(session)
    cleaned = svc.cleanup_expired_reels()
    assert cleaned == 1
    archived = session.query(models.ArchivedReel).filter_by(reel_id=reel.id).first()
    assert archived is not None
    assert archived.view_count == 3


def test_fact_override_status(session, test_user):
    fact = models.Fact(claim="test claim", submitter_id=test_user["id"])
    session.add(fact)
    session.commit()
    session.refresh(fact)

    updated = FactCheckingService.override_fact_status(
        session,
        fact_id=fact.id,
        admin_id=test_user["id"],
        status=FactCheckStatus.VERIFIED,
        note="manual override",
    )
    assert updated.status == FactCheckStatus.VERIFIED
    assert "manual override" in (updated.description or "")
