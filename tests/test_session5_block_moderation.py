import datetime

import pytest
from fastapi import status

from app import models
from app.oauth2 import create_access_token


def _auth_headers(user_id: int):
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_block_user_and_unblock_flow(client, session, test_user, test_user2, monkeypatch):
    """Block another user, inspect block info, then unblock and ensure removal."""
    monkeypatch.setattr(
        "app.routers.block.unblock_user",
        type("Obj", (), {"apply_async": staticmethod(lambda *_, **__: None)}),
    )

    payload = {
        "blocked_id": test_user2.id,
        "block_type": models.BlockType.FULL.value if hasattr(models, "BlockType") else "full",
        "duration": 1,
        "duration_unit": "days",
    }
    headers = _auth_headers(test_user.id)

    created = client.post("/block/", json=payload, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    block_id = created.json()["blocked_id"]
    assert block_id == test_user2.id
    assert created.json().get("ends_at") is not None

    info = client.get(f"/block/{test_user2.id}", headers=headers)
    assert info.status_code == 200
    assert info.json()["blocked_id"] == test_user2.id

    delete = client.delete(f"/block/{test_user2.id}", headers=headers)
    assert delete.status_code == status.HTTP_204_NO_CONTENT

    missing = client.get(f"/block/{test_user2.id}", headers=headers)
    assert missing.status_code == status.HTTP_404_NOT_FOUND


def test_block_self_rejected(client, test_user):
    """Blocking self should return 400 with clear error."""
    headers = _auth_headers(test_user.id)
    payload = {"blocked_id": test_user.id}
    res = client.post("/block/", json=payload, headers=headers)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot block yourself" in res.json()["detail"].lower()


def test_appeal_creation_and_duplicate(client, session, test_user, test_user2, monkeypatch):
    """Blocked user can appeal once; duplicates rejected; non-owner forbidden."""
    monkeypatch.setattr(
        "app.routers.block.unblock_user",
        type("Obj", (), {"apply_async": staticmethod(lambda *_, **__: None)}),
    )
    # user2 blocks user1
    payload = {"blocked_id": test_user.id, "block_type": "full"}
    headers_user2 = _auth_headers(test_user2.id)
    created = client.post("/block/", json=payload, headers=headers_user2)
    assert created.status_code == status.HTTP_201_CREATED
    block = session.query(models.Block).filter_by(blocker_id=test_user2.id).first()
    block_id = block.id

    # blocked user appeals
    appeal_payload = {"block_id": block.id, "reason": "please unblock"}
    headers_user = _auth_headers(test_user.id)
    first = client.post("/block/appeal", json=appeal_payload, headers=headers_user)
    assert first.status_code == status.HTTP_201_CREATED

    # duplicate appeal rejected
    dup = client.post("/block/appeal", json=appeal_payload, headers=headers_user)
    assert dup.status_code == status.HTTP_400_BAD_REQUEST

    # non-owner cannot appeal
    forbidden = client.post("/block/appeal", json=appeal_payload, headers=headers_user2)
    assert forbidden.status_code == status.HTTP_403_FORBIDDEN


def test_moderator_can_list_and_review_appeals(
    client, session, test_user, test_user2, monkeypatch
):
    """Moderator sees pending appeals and can approve to remove the block."""
    monkeypatch.setattr(
        "app.routers.block.unblock_user",
        type("Obj", (), {"apply_async": staticmethod(lambda *_, **__: None)}),
    )
    # Create block with user2 blocker, user1 blocked
    payload = {"blocked_id": test_user.id, "block_type": "full"}
    headers_user2 = _auth_headers(test_user2.id)
    client.post("/block/", json=payload, headers=headers_user2)
    block = session.query(models.Block).filter_by(blocker_id=test_user2.id).first()
    block_id = block.id

    # Blocked user files appeal
    appeal_payload = {"block_id": block.id, "reason": "appeal reason"}
    headers_user = _auth_headers(test_user.id)
    client.post("/block/appeal", json=appeal_payload, headers=headers_user)

    # Promote user2 to moderator for review
    session.query(models.User).filter_by(id=test_user2.id).update(
        {"role": models.UserRole.MODERATOR}
    )
    session.commit()
    moderator = session.get(models.User, test_user2.id)

    from app.routers import block as block_router
    from app.modules.moderation import schemas as mod_schemas

    appeals = block_router.get_block_appeals(
        db=session, current_user=moderator, skip=0, limit=10
    )
    assert appeals

    appeal_id = session.query(models.BlockAppeal).first().id

    reviewed = block_router.review_block_appeal(
        appeal_id=appeal_id,
        review=mod_schemas.BlockAppealReview(status=models.AppealStatus.APPROVED),
        db=session,
        current_user=moderator,
    )
    assert reviewed.status == models.AppealStatus.APPROVED
    remaining = session.query(models.Block).filter_by(id=block_id).first()
    assert remaining is None
