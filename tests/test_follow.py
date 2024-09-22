import pytest
from app import models


def test_follow_user(authorized_client, test_user, test_user2, session):
    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 201
    assert response.json()["message"] == "Successfully followed user"

    follow = (
        session.query(models.Follow)
        .filter(
            models.Follow.follower_id == test_user["id"],
            models.Follow.followed_id == test_user2["id"],
        )
        .first()
    )
    assert follow is not None


def test_unfollow_user(authorized_client, test_user, test_user2, session):
    # First, follow the user
    authorized_client.post(f"/follow/{test_user2['id']}")

    # Now unfollow
    response = authorized_client.delete(f"/follow/{test_user2['id']}")
    assert response.status_code == 204

    follow = (
        session.query(models.Follow)
        .filter(
            models.Follow.follower_id == test_user["id"],
            models.Follow.followed_id == test_user2["id"],
        )
        .first()
    )
    assert follow is None


def test_cannot_follow_self(authorized_client, test_user):
    response = authorized_client.post(f"/follow/{test_user['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot follow yourself"


def test_cannot_follow_twice(authorized_client, test_user, test_user2):
    # First follow
    authorized_client.post(f"/follow/{test_user2['id']}")

    # Try to follow again
    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "You already follow this user"


def test_unfollow_non_followed_user(authorized_client, test_user2):
    response = authorized_client.delete(f"/follow/{test_user2['id']}")
    assert response.status_code == 404
    assert response.json()["detail"] == "You do not follow this user"


def test_follow_non_existent_user(authorized_client):
    non_existent_user_id = 9999  # Assuming this ID doesn't exist
    response = authorized_client.post(f"/follow/{non_existent_user_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "User to follow not found"


@pytest.mark.parametrize("endpoint", ["/follow/0", "/follow/-1"])
def test_invalid_user_id(authorized_client, endpoint):
    response = authorized_client.post(endpoint)
    assert response.status_code == 422  # Now expecting 422 Unprocessable Entity
    assert "Invalid user ID" in response.json()["detail"]


def test_non_integer_user_id(authorized_client):
    response = authorized_client.post("/follow/abc")
    assert response.status_code == 422  # Expecting 422 for non-integer values


def test_unauthorized_follow(client, test_user2):
    response = client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_follow_user_check_email_notification(
    authorized_client, test_user, test_user2, mocker
):
    # Mock the send_email_notification function
    mock_send_email = mocker.patch("app.notifications.send_email_notification")

    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 201

    # Check if the email notification was called with correct parameters
    mock_send_email.assert_called_once_with(
        to=test_user2["email"],
        subject="New Follower",
        body=f"You have a new follower: {test_user['username']}",
    )


def test_unfollow_user_no_email_notification(
    authorized_client, test_user, test_user2, mocker
):
    # First, follow the user
    authorized_client.post(f"/follow/{test_user2['id']}")

    # Mock the send_email_notification function
    mock_send_email = mocker.patch("app.notifications.send_email_notification")

    # Now unfollow
    response = authorized_client.delete(f"/follow/{test_user2['id']}")
    assert response.status_code == 204

    # Check that no email notification was sent for unfollowing
    mock_send_email.assert_not_called()
