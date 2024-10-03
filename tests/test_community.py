import pytest
from fastapi import status
from app.schemas import (
    CommunityOut,
    ReelOut,
    ArticleOut,
    PostOut,
    CommunityInvitationOut,
    UserOut,
)
import logging
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)


@pytest.fixture
def test_community(authorized_client):
    community_data = {
        "name": "Test Community",
        "description": "This is a test community",
    }
    res = authorized_client.post("/communities", json=community_data)
    assert res.status_code == status.HTTP_201_CREATED
    new_community = res.json()
    return new_community


@pytest.fixture
def test_reel(authorized_client, test_community):
    reel_data = {
        "title": "Test Reel",
        "video_url": "http://example.com/test_video.mp4",
        "description": "This is a test reel",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/reels", json=reel_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    new_reel = res.json()
    return new_reel


@pytest.fixture
def test_article(authorized_client, test_community):
    article_data = {
        "title": "Test Article",
        "content": "This is the content of the test article",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/articles", json=article_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    new_article = res.json()
    return new_article


@pytest.fixture
def test_community_post(authorized_client, test_community):
    post_data = {
        "title": "Test Community Post",
        "content": "This is a test post in the community",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/posts", json=post_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    new_post = res.json()
    return new_post


def test_create_reel(authorized_client, test_community):
    reel_data = {
        "title": "New Test Reel",
        "video_url": "http://example.com/new_test_video.mp4",
        "description": "This is a new test reel",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/reels", json=reel_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    created_reel = res.json()
    assert created_reel["title"] == reel_data["title"]
    assert created_reel["video_url"] == reel_data["video_url"]
    assert created_reel["description"] == reel_data["description"]
    assert "id" in created_reel
    assert "created_at" in created_reel
    assert "owner_id" in created_reel
    assert "owner" in created_reel
    assert "community" in created_reel


def test_get_community_reels(authorized_client, test_community, test_reel):
    res = authorized_client.get(f"/communities/{test_community['id']}/reels")
    assert res.status_code == status.HTTP_200_OK
    reels = res.json()
    assert isinstance(reels, list)
    assert len(reels) > 0
    assert all(isinstance(reel, dict) for reel in reels)
    assert all("id" in reel for reel in reels)
    assert all("title" in reel for reel in reels)
    assert all("video_url" in reel for reel in reels)
    assert all("description" in reel for reel in reels)
    assert all("created_at" in reel for reel in reels)
    assert all("owner_id" in reel for reel in reels)
    assert all("owner" in reel for reel in reels)
    assert all("community" in reel for reel in reels)


def test_create_article(authorized_client, test_community):
    article_data = {
        "title": "New Test Article",
        "content": "This is the content of the new test article",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/articles", json=article_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    created_article = res.json()
    assert created_article["title"] == article_data["title"]
    assert created_article["content"] == article_data["content"]
    assert "id" in created_article
    assert "created_at" in created_article
    assert "author_id" in created_article
    assert "author" in created_article
    assert "community" in created_article


def test_get_community_articles(authorized_client, test_community, test_article):
    res = authorized_client.get(f"/communities/{test_community['id']}/articles")
    assert res.status_code == status.HTTP_200_OK
    articles = res.json()
    assert isinstance(articles, list)
    assert len(articles) > 0
    assert all(isinstance(article, dict) for article in articles)
    assert all("id" in article for article in articles)
    assert all("title" in article for article in articles)
    assert all("content" in article for article in articles)
    assert all("created_at" in article for article in articles)
    assert all("author_id" in article for article in articles)
    assert all("author" in article for article in articles)
    assert all("community" in article for article in articles)


def test_create_community_post(authorized_client, test_community):
    post_data = {
        "title": "New Test Community Post",
        "content": "This is a new test post in the community",
        "community_id": test_community["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/posts", json=post_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    created_post = res.json()
    assert created_post["title"] == post_data["title"]
    assert created_post["content"] == post_data["content"]
    assert "id" in created_post
    assert "created_at" in created_post
    assert "owner_id" in created_post
    assert "owner" in created_post
    assert "community" in created_post


def test_get_community_posts(authorized_client, test_community, test_community_post):
    res = authorized_client.get(f"/communities/{test_community['id']}/posts")
    assert res.status_code == status.HTTP_200_OK
    posts = res.json()
    assert isinstance(posts, list)
    assert len(posts) > 0
    assert all(isinstance(post, dict) for post in posts)
    assert all("id" in post for post in posts)
    assert all("title" in post for post in posts)
    assert all("content" in post for post in posts)
    assert all("created_at" in post for post in posts)
    assert all("owner_id" in post for post in posts)
    assert all("owner" in post for post in posts)
    assert all("community" in post for post in posts)


def test_create_reel_not_member(authorized_client, test_community, test_user2, client):
    # Login as the second user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Try to create a reel as a non-member
    headers = {"Authorization": f"Bearer {token}"}
    reel_data = {
        "title": "Unauthorized Reel",
        "video_url": "http://example.com/unauthorized_video.mp4",
        "description": "This reel should not be allowed",
        "community_id": test_community["id"],
    }
    res = client.post(
        f"/communities/{test_community['id']}/reels", json=reel_data, headers=headers
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_create_community(authorized_client):
    community_data = {
        "name": "New Test Community",
        "description": "This is a new test community",
    }
    res = authorized_client.post("/communities", json=community_data)
    assert res.status_code == status.HTTP_201_CREATED
    created_community = res.json()
    assert created_community["name"] == community_data["name"]
    assert created_community["description"] == community_data["description"]
    assert "id" in created_community
    assert "created_at" in created_community
    assert "owner_id" in created_community
    assert "owner" in created_community
    assert "member_count" in created_community
    assert created_community["member_count"] == 1  # Owner is automatically a member


def test_get_communities(authorized_client, test_community):
    res = authorized_client.get("/communities")
    assert res.status_code == status.HTTP_200_OK
    communities = res.json()
    assert isinstance(communities, list)
    assert len(communities) > 0
    assert all(isinstance(community, dict) for community in communities)
    assert all("id" in community for community in communities)
    assert all("name" in community for community in communities)
    assert all("description" in community for community in communities)
    assert all("created_at" in community for community in communities)
    assert all("owner_id" in community for community in communities)
    assert all("owner" in community for community in communities)
    assert all("member_count" in community for community in communities)


def test_get_one_community(authorized_client, test_community):
    res = authorized_client.get(f"/communities/{test_community['id']}")
    assert res.status_code == status.HTTP_200_OK
    fetched_community = res.json()
    assert fetched_community["id"] == test_community["id"]
    assert fetched_community["name"] == test_community["name"]
    assert "description" in fetched_community
    assert "created_at" in fetched_community
    assert "owner_id" in fetched_community
    assert "owner" in fetched_community
    assert "member_count" in fetched_community


def test_update_community(authorized_client, test_community):
    updated_data = {
        "name": "Updated Test Community",
        "description": "This is an updated test community",
    }
    res = authorized_client.put(
        f"/communities/{test_community['id']}", json=updated_data
    )
    assert res.status_code == status.HTTP_200_OK
    updated_community = res.json()
    assert updated_community["name"] == updated_data["name"]
    assert updated_community["description"] == updated_data["description"]
    assert "id" in updated_community
    assert "created_at" in updated_community
    assert "owner_id" in updated_community
    assert "owner" in updated_community
    assert "member_count" in updated_community


def test_delete_community(authorized_client, test_community):
    res = authorized_client.delete(f"/communities/{test_community['id']}")
    assert res.status_code == status.HTTP_204_NO_CONTENT


def test_join_and_leave_community(
    authorized_client, test_community, test_user2, client
):
    # Ensure test_user2 is not the owner of the community
    assert (
        test_community["owner_id"] != test_user2["id"]
    ), "test_user2 should not be the owner of the community"

    # Login as the second user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Create a new client with the second user's token
    second_user_client = TestClient(client.app)
    second_user_client.headers = {
        **second_user_client.headers,
        "Authorization": f"Bearer {token}",
    }

    # Check initial membership status
    get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
    assert get_community_res.status_code == status.HTTP_200_OK
    community_data = get_community_res.json()

    # Ensure the user is not already a member
    assert not any(
        member["id"] == test_user2["id"] for member in community_data["members"]
    ), "User is already a member of the community"

    # Join the community as the second user
    join_res = second_user_client.post(f"/communities/{test_community['id']}/join")
    assert (
        join_res.status_code == status.HTTP_200_OK
    ), f"Failed to join: {join_res.json()}"
    assert join_res.json()["message"] == "Joined the community successfully"

    # Verify membership after joining
    get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
    assert get_community_res.status_code == status.HTTP_200_OK
    community_data = get_community_res.json()
    assert any(
        member["id"] == test_user2["id"] for member in community_data["members"]
    ), "User should be a member after joining"

    # Leave the community
    leave_res = second_user_client.post(f"/communities/{test_community['id']}/leave")
    assert (
        leave_res.status_code == status.HTTP_200_OK
    ), f"Failed to leave: {leave_res.json()}"
    assert leave_res.json()["message"] == "Left the community successfully"

    # Verify membership after leaving
    get_community_res = second_user_client.get(f"/communities/{test_community['id']}")
    assert get_community_res.status_code == status.HTTP_200_OK
    community_data = get_community_res.json()
    assert not any(
        member["id"] == test_user2["id"] for member in community_data["members"]
    ), "User should not be a member after leaving"

    # Try to leave again (should fail)
    leave_again_res = second_user_client.post(
        f"/communities/{test_community['id']}/leave"
    )
    assert leave_again_res.status_code == status.HTTP_400_BAD_REQUEST


def test_owner_cannot_leave_community(authorized_client, test_community):
    res = authorized_client.post(f"/communities/{test_community['id']}/leave")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Owner cannot leave the community"


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
        ({"name": "No Description"}, status.HTTP_201_CREATED),
        ({"description": "No Name"}, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ],
)
def test_create_community_validation(
    authorized_client, community_data, expected_status
):
    res = authorized_client.post("/communities", json=community_data)
    assert res.status_code == expected_status


def test_get_community_unauthorized(client):
    res = client.get("/communities")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_update_community_not_owner(
    authorized_client, test_community, test_user2, client
):
    # Login as the second user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Try to update the community as the second user
    headers = {"Authorization": f"Bearer {token}"}
    updated_data = {
        "name": "Unauthorized Update",
        "description": "This update should not be allowed",
    }
    res = client.put(
        f"/communities/{test_community['id']}", json=updated_data, headers=headers
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_delete_community_not_owner(
    authorized_client, test_community, test_user2, client
):
    # Login as the second user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Try to delete the community as the second user
    headers = {"Authorization": f"Bearer {token}"}
    res = client.delete(f"/communities/{test_community['id']}", headers=headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_create_content_nonexistent_community(authorized_client):
    nonexistent_id = 99999  # Assuming this ID doesn't exist
    reel_data = {
        "title": "Test Reel",
        "video_url": "http://example.com/test_video.mp4",
        "description": "This is a test reel",
    }
    res = authorized_client.post(f"/communities/{nonexistent_id}/reels", json=reel_data)
    assert res.status_code == status.HTTP_404_NOT_FOUND

    article_data = {
        "title": "Test Article",
        "content": "This is the content of the test article",
    }
    res = authorized_client.post(
        f"/communities/{nonexistent_id}/articles", json=article_data
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND

    post_data = {
        "title": "Test Community Post",
        "content": "This is a test post in the community",
    }
    res = authorized_client.post(f"/communities/{nonexistent_id}/posts", json=post_data)
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.fixture
def test_invitation(authorized_client, test_community, test_user2):
    invitation_data = {
        "community_id": test_community["id"],
        "invitee_id": test_user2["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/invite", json=invitation_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    new_invitation = res.json()
    return new_invitation


def test_invite_friend_to_community(authorized_client, test_community, test_user2):
    invitation_data = {
        "community_id": test_community["id"],
        "invitee_id": test_user2["id"],
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/invite", json=invitation_data
    )
    assert res.status_code == status.HTTP_201_CREATED
    created_invitation = res.json()
    assert created_invitation["community_id"] == test_community["id"]
    assert created_invitation["invitee_id"] == test_user2["id"]
    assert "id" in created_invitation
    assert "inviter_id" in created_invitation
    assert created_invitation["status"] == "pending"
    assert "created_at" in created_invitation


def test_get_user_invitations(authorized_client, test_invitation, test_user2, client):
    # Login as the invited user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Get user invitations
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get(
        "/communities/user-invitations", headers=headers, allow_redirects=True
    )

    # Check status code and response content
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"Expected 200, got {res.status_code}. Response: {res.text}"

    invitations = res.json()
    assert isinstance(invitations, list), f"Expected a list, got {type(invitations)}"

    if test_invitation:
        assert len(invitations) > 0, "Expected at least one invitation"
        assert any(
            inv["id"] == test_invitation["id"] for inv in invitations
        ), "Test invitation not found in response"

    # Validate invitation schema
    for invitation in invitations:
        assert "id" in invitation
        assert "community_id" in invitation
        assert "inviter_id" in invitation
        assert "invitee_id" in invitation
        assert "status" in invitation
        assert "created_at" in invitation
        assert "community" in invitation
        assert "inviter" in invitation
        assert "invitee" in invitation


def test_accept_invitation(authorized_client, test_invitation, test_user2, client):
    # Login as the invited user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Accept the invitation
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        f"/communities/invitations/{test_invitation['id']}/accept", headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    response_data = res.json()
    assert response_data["message"] == "Invitation accepted successfully"

    # Verify that the user is now a member of the community
    res = client.get(f"/communities/{test_invitation['community_id']}", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    community_data = res.json()
    assert any(member["id"] == test_user2["id"] for member in community_data["members"])


def test_reject_invitation(authorized_client, test_invitation, test_user2, client):
    # Login as the invited user
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Reject the invitation
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        f"/communities/invitations/{test_invitation['id']}/reject", headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    response_data = res.json()
    assert response_data["message"] == "Invitation rejected successfully"

    # Verify that the user is not a member of the community
    res = client.get(f"/communities/{test_invitation['community_id']}", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    community_data = res.json()
    assert all(member["id"] != test_user2["id"] for member in community_data["members"])


def test_invite_non_existing_user(authorized_client, test_community):
    invitation_data = {
        "community_id": test_community["id"],
        "invitee_id": 99999,  # Non-existing user ID
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/invite", json=invitation_data
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_invite_already_member(authorized_client, test_community, test_user):
    invitation_data = {
        "community_id": test_community["id"],
        "invitee_id": test_user["id"],  # The user who created the community
    }
    res = authorized_client.post(
        f"/communities/{test_community['id']}/invite", json=invitation_data
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_non_member_invite(authorized_client, test_community, test_user2, client):
    # Login as the second user (non-member)
    login_data = {"username": test_user2["email"], "password": test_user2["password"]}
    login_res = client.post("/login", data=login_data)
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json().get("access_token")

    # Try to invite someone as a non-member
    headers = {"Authorization": f"Bearer {token}"}
    invitation_data = {
        "community_id": test_community["id"],
        "invitee_id": test_user2["id"],
    }
    res = client.post(
        f"/communities/{test_community['id']}/invite",
        json=invitation_data,
        headers=headers,
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
