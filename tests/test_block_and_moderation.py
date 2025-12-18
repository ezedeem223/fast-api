from datetime import datetime, timedelta

import pytest

from types import SimpleNamespace
import pytest

from app.main import app
from app import oauth2
from app import models, schemas


@pytest.fixture
def admin_client(authorized_client, test_user):
    admin_user = SimpleNamespace(**test_user, is_admin=True, is_moderator=True)
    app.dependency_overrides[oauth2.get_current_user] = lambda: admin_user
    yield authorized_client
    app.dependency_overrides.pop(oauth2.get_current_user, None)


def test_block_and_unblock_flow(admin_client, test_user2, session):
    # block user2
    payload = {"blocked_id": test_user2["id"], "block_type": "full"}
    res = admin_client.post("/block/", json=payload)
    assert res.status_code == 201

    block_record = (
        session.query(models.Block)
        .filter_by(blocker_id=1, blocked_id=test_user2["id"])
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
    payload = {"blocked_id": test_user["id"], "block_type": "full"}
    res = admin_client.post("/block/", json=payload)
    assert res.status_code == 400
    assert res.json()["detail"] == "You cannot block yourself"


def test_warn_and_ban_user_routes(admin_client, test_user2, session):
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
    assert session.query(models.UserBan).filter_by(user_id=test_user2["id"]).count() == 1
