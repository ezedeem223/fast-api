from fastapi import status

from app.modules.community import CommunityMember, CommunityRole
from tests.conftest import TestingSessionLocal


def _login(client, email: str, password: str) -> dict:
    """Return authorization headers for the given user."""
    response = client.post(
        "/login", data={"username": email, "password": password}
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_community(authorized_client, name: str = "Test Community") -> dict:
    payload = {"name": name, "description": f"{name} description", "category_id": None}
    response = authorized_client.post("/communities", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def test_create_community_returns_owner_details(authorized_client):
    community = _create_community(authorized_client, "Tech Circle")

    assert community["name"] == "Tech Circle"
    assert community["member_count"] == 1
    assert community["members"][0]["role"].lower() == "owner"
    assert community["members"][0]["user"]["is_verified"] is True


def test_list_communities_includes_created(authorized_client):
    community = _create_community(authorized_client, "Writers Hub")

    response = authorized_client.get("/communities")
    assert response.status_code == status.HTTP_200_OK

    ids = [item["id"] for item in response.json()]
    assert community["id"] in ids


def test_join_community_adds_member(authorized_client, client, test_user2):
    community = _create_community(authorized_client, "Joinable Hub")

    headers = _login(client, test_user2["email"], test_user2["password"])
    response = client.post(
        f"/communities/{community['id']}/join", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Successfully joined the community"

    with TestingSessionLocal() as db:
        membership = (
            db.query(CommunityMember)
            .filter_by(community_id=community["id"], user_id=test_user2["id"])
            .first()
        )
        assert membership is not None
        assert membership.role == CommunityRole.MEMBER


def test_join_community_twice_is_prevented(
    authorized_client, client, test_user2
):
    community = _create_community(authorized_client, "Exclusive Hub")
    headers = _login(client, test_user2["email"], test_user2["password"])

    first = client.post(f"/communities/{community['id']}/join", headers=headers)
    assert first.status_code == status.HTTP_200_OK

    second = client.post(f"/communities/{community['id']}/join", headers=headers)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert second.json()["detail"] == "You are already a member of this community"


def test_create_post_requires_membership(
    authorized_client, client, test_user2
):
    community = _create_community(authorized_client, "Writers Lounge")
    post_payload = {"title": "Announcements", "content": "Welcome aboard!"}

    non_member_headers = _login(
        client, test_user2["email"], test_user2["password"]
    )
    denied = client.post(
        f"/communities/{community['id']}/post",
        json=post_payload,
        headers=non_member_headers,
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert (
        denied.json()["detail"]
        == "You must be a member of the community to create a post"
    )

    allowed = authorized_client.post(
        f"/communities/{community['id']}/post", json=post_payload
    )
    assert allowed.status_code == status.HTTP_201_CREATED
    body = allowed.json()
    assert body["community_id"] == community["id"]
    assert body["content"] == post_payload["content"]
