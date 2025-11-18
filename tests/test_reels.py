import pytest
from datetime import datetime, timedelta, timezone

from app import models
from tests.conftest import TestingSessionLocal


@pytest.fixture
def community(session, test_user):
    community = models.Community(
        name=f"community-{test_user['id']}",
        description="Ephemeral stories",
        owner_id=test_user["id"],
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    membership = models.CommunityMember(
        community_id=community.id,
        user_id=test_user["id"],
        role=models.CommunityRole.OWNER,
    )
    session.add(membership)
    session.commit()
    return community


def _create_reel(session, owner_id: int, community_id: int, *, expires_at, is_active: bool = True):
    reel = models.Reel(
        title="seed",
        video_url="https://videos.local/story.mp4",
        description="seed",
        owner_id=owner_id,
        community_id=community_id,
        expires_at=expires_at,
        is_active=is_active,
    )
    session.add(reel)
    session.commit()
    session.refresh(reel)
    return reel


def test_create_reel_endpoint(authorized_client, community):
    payload = {
        "title": "Morning update",
        "video_url": "https://videos.local/morning.mp4",
        "description": "coffee thoughts",
        "community_id": community.id,
        "expires_in_hours": 2,
    }
    response = authorized_client.post("/reels/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["community_id"] == community.id
    assert data["is_active"] is True


def test_list_active_reels_filters_expired(authorized_client, session, community, test_user):
    now = datetime.now(timezone.utc)
    active = _create_reel(session, test_user["id"], community.id, expires_at=now + timedelta(hours=1))
    active_id = active.id
    _create_reel(session, test_user["id"], community.id, expires_at=now - timedelta(hours=1))

    response = authorized_client.get(f"/reels/active?community_id={community.id}")
    assert response.status_code == 200
    reels = response.json()
    assert len(reels) == 1
    assert reels[0]["id"] == active_id


def test_delete_reel_marks_inactive(authorized_client, session, community, test_user):
    now = datetime.now(timezone.utc)
    reel = _create_reel(session, test_user["id"], community.id, expires_at=now + timedelta(hours=1))
    reel_id = reel.id

    response = authorized_client.delete(f"/reels/{reel_id}")
    assert response.status_code == 200

    with TestingSessionLocal() as verify_session:
        stored = (
            verify_session.query(models.Reel.is_active)
            .filter(models.Reel.id == reel_id)
            .scalar()
        )
        assert stored is False


def test_increment_view_count(authorized_client, session, community, test_user):
    now = datetime.now(timezone.utc)
    reel = _create_reel(session, test_user["id"], community.id, expires_at=now + timedelta(hours=1))
    reel_id = reel.id

    response = authorized_client.post(f"/reels/{reel_id}/view")
    assert response.status_code == 200
    assert response.json()["view_count"] == 1

    with TestingSessionLocal() as verify_session:
        view_count = (
            verify_session.query(models.Reel.view_count)
            .filter(models.Reel.id == reel_id)
            .scalar()
        )
        assert view_count == 1
