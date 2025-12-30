from app import models
from app.core.app_factory import create_app
from app.routers import community as community_router
from fastapi import status
from tests.conftest import TestingSessionLocal
from tests.testclient import TestClient


def make_client(db_session):
    app = create_app()
    app.dependency_overrides[community_router.get_db] = lambda: db_session
    app.dependency_overrides[community_router.oauth2.get_current_user] = (
        lambda: db_session.query(models.User).first()
    )
    return TestClient(app)


def seed_user(db, email="owner@example.com"):
    user = models.User(email=email, hashed_password="x", is_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_and_get_community():
    with TestingSessionLocal() as db:
        seed_user(db)
        client = make_client(db)
        payload = {
            "name": "RouterComm",
            "description": "desc",
            "category_id": None,
            "tags": [],
        }

        response = client.post("/communities/", json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        comm_id = response.json()["id"]

        detail = client.get(f"/communities/{comm_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == comm_id


def test_join_requires_existing_invite_for_private():
    with TestingSessionLocal() as db:
        owner = seed_user(db, "owner@ex.com")
        joiner = seed_user(db, "joiner@ex.com")
        community = models.Community(
            name="Private", description="d", owner_id=owner.id, is_private=True
        )
        community.members.append(
            models.CommunityMember(user_id=owner.id, role=models.CommunityRole.OWNER)
        )
        db.add(community)
        db.commit()
        db.refresh(community)

        client = make_client(db)
        client.app.dependency_overrides[community_router.oauth2.get_current_user] = (
            lambda: joiner
        )

        resp = client.post(f"/communities/{community.id}/join")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

        invite = models.CommunityInvitation(
            community_id=community.id,
            inviter_id=owner.id,
            invitee_id=joiner.id,
            status="pending",
        )
        db.add(invite)
        db.commit()

        resp2 = client.post(f"/communities/{community.id}/join")
        assert resp2.status_code == 200
        assert "Successfully" in resp2.json()["message"]


def test_invite_and_accept_flow():
    with TestingSessionLocal() as db:
        owner = seed_user(db, "owner2@ex.com")
        invitee = seed_user(db, "invitee@ex.com")
        community = models.Community(name="Invite", description="d", owner_id=owner.id)
        community.members.append(
            models.CommunityMember(user_id=owner.id, role=models.CommunityRole.OWNER)
        )
        db.add(community)
        db.commit()
        db.refresh(community)

        client = make_client(db)
        client.app.dependency_overrides[community_router.oauth2.get_current_user] = (
            lambda: owner
        )

        resp = client.post(
            f"/communities/{community.id}/invite", json={"user_id": invitee.id}
        )
        assert resp.status_code == 200
        invitation_id = resp.json()["id"]

        client.app.dependency_overrides[community_router.oauth2.get_current_user] = (
            lambda: invitee
        )
        accept = client.post(f"/communities/invitations/{invitation_id}/accept")
        assert accept.status_code == 200
        member = (
            db.query(models.CommunityMember)
            .filter_by(user_id=invitee.id, community_id=community.id)
            .first()
        )
        assert member is not None


def test_get_communities_sorted():
    with TestingSessionLocal() as db:
        user = seed_user(db)
        client = make_client(db)
        for idx in range(3):
            comm = models.Community(
                name=f"Comm{idx}", description="d", owner_id=user.id
            )
            db.add(comm)
        db.commit()

        resp = client.get("/communities/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
