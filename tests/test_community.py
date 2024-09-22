# import pytest
# from fastapi import status
# from app.schemas import CommunityOut
# import logging
# from fastapi.testclient import TestClient

# logger = logging.getLogger(__name__)


# @pytest.fixture
# def test_user(client):
#     user_data = {
#         "email": "testuser@example.com",
#         "password": "testpassword",
#     }
#     res = client.post("/users", json=user_data)
#     assert res.status_code == status.HTTP_201_CREATED
#     new_user = res.json()
#     new_user["password"] = user_data["password"]
#     return new_user


# @pytest.fixture
# def test_user2(client):
#     user_data = {
#         "email": "testuser2@example.com",
#         "password": "testpassword2",
#     }
#     res = client.post("/users", json=user_data)
#     assert res.status_code == status.HTTP_201_CREATED
#     new_user = res.json()
#     new_user["password"] = user_data["password"]
#     return new_user


# @pytest.fixture
# def token(test_user, client):
#     login_data = {"username": test_user["email"], "password": test_user["password"]}
#     res = client.post("/login", data=login_data)
#     assert res.status_code == status.HTTP_200_OK
#     return res.json().get("access_token")


# @pytest.fixture
# def authorized_client(client, token):
#     client.headers = {**client.headers, "Authorization": f"Bearer {token}"}
#     return client


# @pytest.fixture
# def test_community(authorized_client):
#     community_data = {
#         "name": "Test Community",
#         "description": "This is a test community",
#     }
#     res = authorized_client.post("/communities", json=community_data)
#     assert res.status_code == status.HTTP_201_CREATED
#     new_community = res.json()
#     return new_community


# def test_create_community(authorized_client):
#     community_data = {
#         "name": "New Test Community",
#         "description": "This is a new test community",
#     }
#     res = authorized_client.post("/communities", json=community_data)
#     assert res.status_code == status.HTTP_201_CREATED
#     created_community = res.json()
#     assert created_community["name"] == community_data["name"]
#     assert created_community["description"] == community_data["description"]
#     assert "id" in created_community
#     assert "created_at" in created_community
#     assert "owner_id" in created_community
#     assert "owner" in created_community
#     assert "member_count" in created_community
#     assert created_community["member_count"] == 1  # Owner is automatically a member


# def test_get_communities(authorized_client, test_community):
#     res = authorized_client.get("/communities")
#     assert res.status_code == status.HTTP_200_OK
#     communities = res.json()
#     assert isinstance(communities, list)
#     assert len(communities) > 0
#     assert all(isinstance(community, dict) for community in communities)
#     assert all("id" in community for community in communities)
#     assert all("name" in community for community in communities)
#     assert all("description" in community for community in communities)
#     assert all("created_at" in community for community in communities)
#     assert all("owner_id" in community for community in communities)
#     assert all("owner" in community for community in communities)
#     assert all("member_count" in community for community in communities)


# def test_get_one_community(authorized_client, test_community):
#     res = authorized_client.get(f"/communities/{test_community['id']}")
#     assert res.status_code == status.HTTP_200_OK
#     fetched_community = res.json()
#     assert fetched_community["id"] == test_community["id"]
#     assert fetched_community["name"] == test_community["name"]
#     assert "description" in fetched_community
#     assert "created_at" in fetched_community
#     assert "owner_id" in fetched_community
#     assert "owner" in fetched_community
#     assert "member_count" in fetched_community


# def test_update_community(authorized_client, test_community):
#     updated_data = {
#         "name": "Updated Test Community",
#         "description": "This is an updated test community",
#     }
#     res = authorized_client.put(
#         f"/communities/{test_community['id']}", json=updated_data
#     )
#     assert res.status_code == status.HTTP_200_OK
#     updated_community = res.json()
#     assert updated_community["name"] == updated_data["name"]
#     assert updated_community["description"] == updated_data["description"]
#     assert "id" in updated_community
#     assert "created_at" in updated_community
#     assert "owner_id" in updated_community
#     assert "owner" in updated_community
#     assert "member_count" in updated_community


# def test_delete_community(authorized_client, test_community):
#     res = authorized_client.delete(f"/communities/{test_community['id']}")
#     assert res.status_code == status.HTTP_204_NO_CONTENT


# def test_join_and_leave_community(
#     authorized_client, test_community, test_user2, client
# ):
#     # Ensure test_user2 is not the owner of the community
#     assert (
#         test_community["owner_id"] != test_user2["id"]
#     ), "test_user2 should not be the owner of the community"

#     # Login as the second user
#     login_data = {"username": test_user2["email"], "password": test_user2["password"]}
#     login_res = client.post("/login", data=login_data)
#     assert login_res.status_code == status.HTTP_200_OK
#     token = login_res.json().get("access_token")

#     # Create a new client with the second user's token
#     second_user_client = TestClient(client.app)
#     second_user_client.headers = {
#         **second_user_client.headers,
#         "Authorization": f"Bearer {token}",
#     }

#     # Check initial membership status
#     get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
#     assert get_community_res.status_code == status.HTTP_200_OK
#     community_data = get_community_res.json()

#     # Ensure the user is not already a member
#     assert not any(
#         member["id"] == test_user2["id"] for member in community_data["members"]
#     ), "User is already a member of the community"

#     # Join the community as the second user
#     join_res = second_user_client.post(f"/communities/{test_community['id']}/join")
#     assert (
#         join_res.status_code == status.HTTP_200_OK
#     ), f"Failed to join: {join_res.json()}"
#     assert join_res.json()["message"] == "Joined the community successfully"

#     # Verify membership after joining
#     get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
#     assert get_community_res.status_code == status.HTTP_200_OK
#     community_data = get_community_res.json()
#     assert any(
#         member["id"] == test_user2["id"] for member in community_data["members"]
#     ), "User should be a member after joining"

#     # Leave the community
#     leave_res = second_user_client.post(f"/communities/{test_community['id']}/leave")
#     assert (
#         leave_res.status_code == status.HTTP_200_OK
#     ), f"Failed to leave: {leave_res.json()}"
#     assert leave_res.json()["message"] == "Left the community successfully"

#     # Verify membership after leaving
#     get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
#     assert get_community_res.status_code == status.HTTP_200_OK
#     community_data = get_community_res.json()
#     assert not any(
#         member["id"] == test_user2["id"] for member in community_data["members"]
#     ), "User should not be a member after leaving"

#     # Try to leave again (should fail)
#     leave_again_res = second_user_client.post(
#         f"/communities/{test_community['id']}/leave"
#     )
#     assert leave_again_res.status_code == status.HTTP_400_BAD_REQUEST


# def test_owner_cannot_leave_community(authorized_client, test_community):
#     res = authorized_client.post(f"/communities/{test_community['id']}/leave")
#     assert res.status_code == status.HTTP_400_BAD_REQUEST
#     assert res.json()["detail"] == "Owner cannot leave the community"


# @pytest.mark.parametrize(
#     "community_data, expected_status",
#     [
#         (
#             {"name": "Valid Community", "description": "Valid description"},
#             status.HTTP_201_CREATED,
#         ),
#         (
#             {"name": "", "description": "Invalid name"},
#             status.HTTP_422_UNPROCESSABLE_ENTITY,
#         ),
#         ({"name": "No Description"}, status.HTTP_201_CREATED),
#         ({"description": "No Name"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
#     ],
# )
# def test_create_community_validation(
#     authorized_client, community_data, expected_status
# ):
#     res = authorized_client.post("/communities", json=community_data)
#     assert res.status_code == expected_status


# def test_get_community_unauthorized(client):
#     res = client.get("/communities")
#     assert res.status_code == status.HTTP_401_UNAUTHORIZED


# def test_update_community_not_owner(
#     authorized_client, test_community, test_user2, client
# ):
#     # Login as the second user
#     login_data = {"username": test_user2["email"], "password": test_user2["password"]}
#     login_res = client.post("/login", data=login_data)
#     assert login_res.status_code == status.HTTP_200_OK
#     token = login_res.json().get("access_token")

#     # Try to update the community as the second user
#     headers = {"Authorization": f"Bearer {token}"}
#     updated_data = {
#         "name": "Unauthorized Update",
#         "description": "This update should not be allowed",
#     }
#     res = client.put(
#         f"/communities/{test_community['id']}", json=updated_data, headers=headers
#     )
#     assert res.status_code == status.HTTP_403_FORBIDDEN


# def test_delete_community_not_owner(
#     authorized_client, test_community, test_user2, client
# ):
#     # Login as the second user
#     login_data = {"username": test_user2["email"], "password": test_user2["password"]}
#     login_res = client.post("/login", data=login_data)
#     assert login_res.status_code == status.HTTP_200_OK
#     token = login_res.json().get("access_token")

#     # Try to delete the community as the second user
#     headers = {"Authorization": f"Bearer {token}"}
#     res = client.delete(f"/communities/{test_community['id']}", headers=headers)
#     assert res.status_code == status.HTTP_403_FORBIDDEN
