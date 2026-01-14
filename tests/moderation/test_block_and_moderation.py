"""Test module for test block and moderation."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import models, oauth2
from app.main import app


@pytest.fixture
def admin_client(authorized_client, test_user):
    """Pytest fixture for admin_client."""
    admin_user = SimpleNamespace(**test_user, is_admin=True, is_moderator=True)
    app.dependency_overrides[oauth2.get_current_user] = lambda: admin_user
    yield authorized_client
    app.dependency_overrides.pop(oauth2.get_current_user, None)


def test_block_and_unblock_flow(admin_client, test_user, test_user2, session):
    # block user2
    """Test case for test block and unblock flow."""
    payload = {"blocked_id": test_user2["id"], "block_type": "full"}
    res = admin_client.post("/block/", json=payload)
    assert res.status_code == 201

    block_record = (
        session.query(models.Block)
        .filter_by(blocker_id=test_user["id"], blocked_id=test_user2["id"])
        .first()
    )
    assert block_record is not None
    assert block_record.blocked_id == test_user2["id"]

    # unblock
    res_del = admin_client.delete(f"/block/{test_user2['id']}")
    assert res_del.status_code == 204
    remaining = (
        session.query(models.Block)
        .filter(models.Block.blocked_id == test_user2["id"])
        .count()
    )
    assert remaining == 0


def test_block_cannot_self_block(admin_client, test_user):
    """Test case for test block cannot self block."""
    payload = {"blocked_id": test_user["id"], "block_type": "full"}
    res = admin_client.post("/block/", json=payload)
    assert res.status_code == 400
    assert res.json()["detail"] == "You cannot block yourself"


def test_warn_and_ban_user_routes(admin_client, test_user2, session):
    """Test case for test warn and ban user routes."""
    warn_res = admin_client.post(
        f"/moderation/warn/{test_user2['id']}", json={"reason": "Language"}
    )
    assert warn_res.status_code == 200

    ban_payload = {
        "reason": "Severe abuse",
        "duration": 2,
        "duration_unit": "days",
        "ban_type": "temporary",
    }
    ban_res = admin_client.post(f"/moderation/ban/{test_user2['id']}", json=ban_payload)
    assert ban_res.status_code == 200
    banned = session.query(models.UserBan).filter_by(user_id=test_user2["id"]).first()
    assert banned is not None
    assert banned.reason == "Severe abuse"

    # ensure ban recorded
    assert (
        session.query(models.UserBan).filter_by(user_id=test_user2["id"]).count() == 1
    )


def test_report_decision_delete(admin_client, session, test_user, test_user2, test_post):
    """Test case for test report decision delete."""
    report = models.Report(
        report_reason="abuse",
        post_id=test_post["id"],
        reporter_id=test_user2["id"],
        reported_user_id=test_user["id"],
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    res = admin_client.put(
        f"/moderation/reports/{report.id}/decision",
        json={"action": "delete", "resolution_notes": "offensive"},
    )
    assert res.status_code == 200

    session.refresh(report)
    post = session.query(models.Post).filter(models.Post.id == test_post["id"]).first()
    assert report.status == models.ReportStatus.RESOLVED
    assert report.is_valid is True
    assert post.is_deleted is True
    assert post.content == "[Deleted]"


def test_unban_user_route(admin_client, session, test_user2):
    """Test case for test unban user route."""
    user = session.query(models.User).filter(models.User.id == test_user2["id"]).first()
    user.current_ban_end = datetime.now(timezone.utc) + timedelta(days=1)
    session.commit()

    res = admin_client.post(f"/moderation/unban/{test_user2['id']}")
    assert res.status_code == 200

    session.refresh(user)
    assert user.current_ban_end is None
