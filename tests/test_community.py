import pytest
from fastapi import status
from app.schemas import CommunityOut
import logging

logger = logging.getLogger(__name__)


@pytest.fixture
def test_user(client):
    # Register a new user
    user_data = {
        "email": "testuser@example.com",
        "password": "testpassword",
    }
    res = client.post("/users", json=user_data)
    assert res.status_code == status.HTTP_201_CREATED

    # Log in to get the token
    login_res = client.post(
        "/login",
        data={"username": user_data["email"], "password": user_data["password"]},
    )
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    assert token is not None  # Ensure that the token is not None

    return {
        "id": res.json()["id"],
        "token": token,
    }


@pytest.fixture
def authorized_client(client, test_user):
    return client, {"Authorization": f"Bearer {test_user['token']}"}


@pytest.fixture
def test_community(authorized_client):
    client, headers = authorized_client
    community_data = {
        "name": "Test Community",
        "description": "This is a test community",
    }
    res = client.post("/communities", json=community_data, headers=headers)
    assert res.status_code == status.HTTP_201_CREATED
    new_community = res.json()
    new_community["user_id"] = test_user["id"]
    return new_community


@pytest.mark.asyncio
async def test_create_community(authorized_client):
    client, headers = authorized_client
    community_data = {
        "name": "New Test Community",
        "description": "This is a new test community",
    }
    res = client.post("/communities", json=community_data, headers=headers)
    assert res.status_code == status.HTTP_201_CREATED
    created_community = res.json()
    assert created_community["name"] == community_data["name"]
    assert created_community["description"] == community_data["description"]

    # Try to create the same community again
    duplicate_res = client.post("/communities", json=community_data, headers=headers)
    assert duplicate_res.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate_res.json()["detail"] == "Community already exists"


@pytest.mark.asyncio
async def test_get_communities(authorized_client, test_community):
    client, headers = authorized_client
    res = client.get("/communities", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    communities = res.json()
    assert isinstance(communities, list)
    assert len(communities) > 0

    # Test pagination
    res = client.get("/communities?skip=0&limit=1", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) == 1

    # Test search
    res = client.get(
        f"/communities?search={test_community['name'][:3]}", headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) > 0
    assert any(comm["name"] == test_community["name"] for comm in res.json())


@pytest.mark.asyncio
async def test_get_one_community(authorized_client, test_community):
    client, headers = authorized_client
    res = client.get(f"/communities/{test_community['id']}", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    fetched_community = res.json()
    assert fetched_community["id"] == test_community["id"]
    assert fetched_community["name"] == test_community["name"]


@pytest.mark.asyncio
async def test_update_community(authorized_client, test_community):
    client, headers = authorized_client
    updated_data = {
        "name": "Updated Test Community",
        "description": "This is an updated test community",
    }
    res = client.put(
        f"/communities/{test_community['id']}", json=updated_data, headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    updated_community = res.json()
    assert updated_community["name"] == updated_data["name"]
    assert updated_community["description"] == updated_data["description"]


@pytest.mark.asyncio
async def test_delete_community(authorized_client, test_community):
    client, headers = authorized_client
    res = client.delete(f"/communities/{test_community['id']}", headers=headers)
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Verify the community is deleted
    res = client.get(f"/communities/{test_community['id']}", headers=headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_join_and_leave_community(authorized_client, test_community):
    client, headers = authorized_client

    # Join the community
    join_res = client.post(f"/communities/{test_community['id']}/join", headers=headers)
    assert join_res.status_code == status.HTTP_200_OK
    assert join_res.json()["message"] == "Joined the community successfully"

    # Try to join the same community again
    duplicate_join_res = client.post(
        f"/communities/{test_community['id']}/join", headers=headers
    )
    assert duplicate_join_res.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        "User is already a member of this community"
        in duplicate_join_res.json()["detail"]
    )

    # Leave the community
    leave_res = client.post(
        f"/communities/{test_community['id']}/leave", headers=headers
    )
    assert leave_res.status_code == status.HTTP_200_OK
    assert leave_res.json()["message"] == "Left the community successfully"

    # Try to leave the community again
    duplicate_leave_res = client.post(
        f"/communities/{test_community['id']}/leave", headers=headers
    )
    assert duplicate_leave_res.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        "User is not a member of this community" in duplicate_leave_res.json()["detail"]
    )


@pytest.mark.asyncio
async def test_owner_cannot_leave_community(authorized_client, test_community):
    client, headers = authorized_client
    res = client.post(f"/communities/{test_community['id']}/leave", headers=headers)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Owner cannot leave the community"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "community_data, expected_status",
    [
        (
            {"name": "Valid Community", "description": "Valid description"},
            status.HTTP_201_CREATED,
        ),
        (
            {"name": "", "description": "Invalid name"},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        ({"name": "No Description"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
        ({"description": "No Name"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ],
)
async def test_create_community_validation(
    authorized_client, community_data, expected_status
):
    client, headers = authorized_client
    res = client.post("/communities", json=community_data, headers=headers)
    assert res.status_code == expected_status


def test_get_community_unauthorized(client):
    res = client.get("/communities")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_update_community_not_owner(client):
    # Create a new user
    new_user_data = {"email": "newuser@example.com", "password": "newuserpassword"}
    new_user_res = client.post("/users", json=new_user_data)
    assert new_user_res.status_code == status.HTTP_201_CREATED
    new_user = new_user_res.json()

    # Login as the new user
    login_res = client.post(
        "/login",
        data={
            "username": new_user_data["email"],
            "password": new_user_data["password"],
        },
    )
    assert login_res.status_code == status.HTTP_200_OK
    new_user_token = login_res.json().get("access_token")

    # Try to update the community as the new user
    headers = {"Authorization": f"Bearer {new_user_token}"}
    updated_data = {
        "name": "Unauthorized Update",
        "description": "This update should not be allowed",
    }
    res = client.put(
        f"/communities/{test_community['id']}", json=updated_data, headers=headers
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_delete_community_not_owner(client):
    # Create a new user
    new_user_data = {
        "email": "anotheruser@example.com",
        "password": "anotheruserpassword",
    }
    new_user_res = client.post("/users", json=new_user_data)
    assert new_user_res.status_code == status.HTTP_201_CREATED
    new_user = new_user_res.json()

    # Login as the new user
    login_res = client.post(
        "/login",
        data={
            "username": new_user_data["email"],
            "password": new_user_data["password"],
        },
    )
    assert login_res.status_code == status.HTTP_200_OK
    new_user_token = login_res.json().get("access_token")

    # Try to delete the community as the new user
    headers = {"Authorization": f"Bearer {new_user_token}"}
    res = client.delete(f"/communities/{test_community['id']}", headers=headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
