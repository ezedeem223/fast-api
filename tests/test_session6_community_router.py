from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.core.config import settings
from app.oauth2 import create_access_token
from tests.conftest import TestingSessionLocal


def _auth_headers(user_id: int) -> dict:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_create_community_with_rules_persists(authorized_client):
    payload = {
        "name": "Rule Hub",
        "description": "With rules",
        "rules": [{"rule": "No spam"}, {"rule": "Be kind"}],
    }
    response = authorized_client.post("/communities", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert {r["rule"] for r in data["rules"]} >= {"No spam", "Be kind"}
    assert data["member_count"] == 1


def test_duplicate_name_rejected(authorized_client):
    base_payload = {"name": "Unique Club", "description": "First"}
    first = authorized_client.post("/communities", json=base_payload)
    assert first.status_code == 201

    dup = authorized_client.post("/communities", json=base_payload)
    assert dup.status_code in (400, 409)
    assert "exists" in dup.json().get("detail", "").lower()


def test_owner_limit_enforced(monkeypatch, authorized_client):
    monkeypatch.setattr(
        "app.services.community.service.settings.MAX_OWNED_COMMUNITIES",
        1,
    )
    payload = {"name": "Limit One", "description": "First"}
    assert authorized_client.post("/communities", json=payload).status_code == 201

    second = authorized_client.post(
        "/communities", json={"name": "Limit Two", "description": "Second"}
    )
    assert second.status_code == 400


def test_invitation_send_and_accept_adds_member(
    authorized_client, client, test_user2
):
    community_resp = authorized_client.post(
        "/communities", json={"name": "Invite Only", "description": "Desc"}
    )
    assert community_resp.status_code == 201
    community = community_resp.json()

    invite_resp = authorized_client.post(
        f"/communities/{community['id']}/invite",
        json={"user_id": test_user2["id"]},
    )
    assert invite_resp.status_code == 200
    invitation_id = invite_resp.json()["id"]

    accept_headers = _auth_headers(test_user2["id"])
    accept = client.post(
        f"/communities/invitations/{invitation_id}/accept",
        headers=accept_headers,
    )
    assert accept.status_code == 200
    body = accept.json()
    assert body["role"].lower() == "member"

    with TestingSessionLocal() as db:
        members = db.query(models.CommunityMember).filter_by(
            community_id=community["id"]
        )
        assert members.count() == 2


def test_expired_invitation_rejected(
    authorized_client, client, test_user2
):
    community_resp = authorized_client.post(
        "/communities", json={"name": "Old Invite", "description": "Desc"}
    )
    assert community_resp.status_code == 201
    community = community_resp.json()
    invite_resp = authorized_client.post(
        f"/communities/{community['id']}/invite",
        json={"user_id": test_user2["id"]},
    )
    invitation_id = invite_resp.json()["id"]

    with TestingSessionLocal() as db:
        invitation = db.get(models.CommunityInvitation, invitation_id)
        invitation.created_at = datetime.now(timezone.utc) - timedelta(
            days=settings.INVITATION_EXPIRY_DAYS + 1
        )
        db.commit()

    accept_headers = _auth_headers(test_user2["id"])
    expired = client.post(
        f"/communities/invitations/{invitation_id}/accept",
        headers=accept_headers,
    )
    assert expired.status_code in (400, 410)
    assert "expired" in expired.json().get("detail", "").lower()


def test_archive_blocks_new_posts(authorized_client):
    community_resp = authorized_client.post(
        "/communities", json={"name": "Archive Me", "description": "Desc"}
    )
    assert community_resp.status_code == 201
    community = community_resp.json()

    archive = authorized_client.put(
        f"/communities/{community['id']}", json={"is_active": False}
    )
    assert archive.status_code == 200

    post_attempt = authorized_client.post(
        f"/communities/{community['id']}/post",
        json={"title": "T", "content": "Body"},
    )
    assert post_attempt.status_code == 403


def test_unarchive_restores_posting(authorized_client):
    community_resp = authorized_client.post(
        "/communities", json={"name": "Unarchive Me", "description": "Desc"}
    )
    assert community_resp.status_code == 201
    community = community_resp.json()
    assert (
        authorized_client.put(
            f"/communities/{community['id']}", json={"is_active": False}
        ).status_code
        == 200
    )

    restored = authorized_client.put(
        f"/communities/{community['id']}", json={"is_active": True}
    )
    assert restored.status_code == 200

    post_resp = authorized_client.post(
        f"/communities/{community['id']}/post",
        json={"title": "T", "content": "Welcome back"},
    )
    assert post_resp.status_code == 201


def test_duplicate_archive_conflict(authorized_client):
    community_resp = authorized_client.post(
        "/communities", json={"name": "Archive Twice", "description": "Desc"}
    )
    assert community_resp.status_code == 201
    community = community_resp.json()
    authorized_client.put(
        f"/communities/{community['id']}", json={"is_active": False}
    )

    second = authorized_client.put(
        f"/communities/{community['id']}", json={"is_active": False}
    )
    assert second.status_code == 409
