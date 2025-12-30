from datetime import datetime, timedelta, timezone

from app import models
from app.modules.moderation import service as moderation_service
from tests.conftest import TestingSessionLocal


def test_clean_expired_blocks_removes_only_past(monkeypatch):
    with TestingSessionLocal() as db:
        now = datetime.now(timezone.utc)
        active = models.Block(blocker_id=1, blocked_id=2, ends_at=None)
        expired = models.Block(blocker_id=1, blocked_id=3, ends_at=now - timedelta(days=1))
        future = models.Block(blocker_id=1, blocked_id=4, ends_at=now + timedelta(days=1))
        db.add_all([active, expired, future])
        db.commit()

        # Avoid analytics side effects
        monkeypatch.setattr(moderation_service, "update_ban_statistics", lambda *a, **k: None)

        removed = moderation_service.clean_expired_blocks(db)
        remaining = db.query(models.Block).all()

        assert removed == 1
        assert any(b.blocked_id == 2 for b in remaining)  # ends_at None stays
        assert any(b.blocked_id == 4 for b in remaining)  # future stays
        assert all(b.blocked_id != 3 for b in remaining)


def test_unblock_user_sets_ends_at(monkeypatch):
    with TestingSessionLocal() as db:
        now = datetime.now(timezone.utc)
        active = models.Block(blocker_id=5, blocked_id=6, ends_at=None)
        expired = models.Block(blocker_id=5, blocked_id=7, ends_at=now - timedelta(days=1))
        db.add_all([active, expired])
        db.commit()

        monkeypatch.setattr(moderation_service, "update_ban_statistics", lambda *a, **k: None)

        updated = moderation_service.unblock_user(db, blocker_id=5, blocked_id=6)
        db.refresh(active)

        assert updated == 1
        assert active.ends_at is not None
        # Expired block untouched
        assert db.query(models.Block).filter(models.Block.blocked_id == 7).one().ends_at == expired.ends_at
