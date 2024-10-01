# import pytest
# from app import models


# def test_follow_user(authorized_client, test_user, test_user2, session):
#     response = authorized_client.post(f"/follow/{test_user2['id']}")
#     assert response.status_code == 201
#     assert response.json()["message"] == "Successfully followed user"

#     follow = (
#         session.query(models.Follow)
#         .filter(
#             models.Follow.follower_id == test_user["id"],
#             models.Follow.followed_id == test_user2["id"],
#         )
#         .first()
#     )
#     assert follow is not None


# def test_unfollow_user(authorized_client, test_user, test_user2, session):
#     # First, follow the user
#     authorized_client.post(f"/follow/{test_user2['id']}")

#     # Now unfollow
#     response = authorized_client.delete(f"/follow/{test_user2['id']}")
#     assert response.status_code == 204

#     follow = (
#         session.query(models.Follow)
#         .filter(
#             models.Follow.follower_id == test_user["id"],
#             models.Follow.followed_id == test_user2["id"],
#         )
#         .first()
#     )
#     assert follow is None


# def test_cannot_follow_self(authorized_client, test_user):
#     response = authorized_client.post(f"/follow/{test_user['id']}")
#     assert response.status_code == 400
#     assert response.json()["detail"] == "You cannot follow yourself"


# def test_cannot_follow_twice(authorized_client, test_user, test_user2):
#     # First follow
#     authorized_client.post(f"/follow/{test_user2['id']}")

#     # Try to follow again
#     response = authorized_client.post(f"/follow/{test_user2['id']}")
#     assert response.status_code == 400
#     assert response.json()["detail"] == "You already follow this user"


# def test_unfollow_non_followed_user(authorized_client, test_user2):
#     response = authorized_client.delete(f"/follow/{test_user2['id']}")
#     assert response.status_code == 404
#     assert response.json()["detail"] == "You do not follow this user"


# def test_follow_non_existent_user(authorized_client):
#     non_existent_user_id = 9999  # Assuming this ID doesn't exist
#     response = authorized_client.post(f"/follow/{non_existent_user_id}")
#     assert response.status_code == 404
#     assert response.json()["detail"] == "User to follow not found"


# @pytest.mark.parametrize("invalid_id", [0, -1])
# def test_invalid_user_id(authorized_client, invalid_id):
#     response = authorized_client.post(f"/follow/{invalid_id}")
#     assert response.status_code == 422
#     assert "Input should be greater than 0" in response.json()["detail"][0]["msg"]


# def test_unauthorized_follow(client, test_user2):
#     response = client.post(f"/follow/{test_user2['id']}")
#     assert response.status_code == 401
#     assert response.json()["detail"] == "Not authenticated"
