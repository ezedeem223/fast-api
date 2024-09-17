import pytest
from fastapi.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from app import schemas, models
from app.database import Base
from app.oauth2 import create_access_token


@pytest.mark.parametrize(
    "community_data, expected_status_code",
    [
        ({"name": "Community 1", "description": "Test Community"}, 201),
        ({"name": "Community 1"}, 400),  # Duplicate name scenario
    ],
)
def test_create_community(authorized_client, community_data, expected_status_code):
    response = authorized_client.post("/communities/", json=community_data)
    assert response.status_code == expected_status_code
    if expected_status_code == 201:
        assert response.json().get("community")["name"] == community_data["name"]
    else:
        assert response.json().get("detail") == "Community already exists"


def test_get_communities(authorized_client, test_community):
    response = authorized_client.get("/communities/")
    assert response.status_code == 200
    communities = response.json()
    assert len(communities) > 0


def test_join_community(authorized_client, test_community):
    community_id = test_community[0].id
    response = authorized_client.post(f"/communities/{community_id}/join")
    assert response.status_code == 200
    assert response.json().get("message") == "Joined the community successfully"


def test_join_non_existent_community(authorized_client):
    response = authorized_client.post("/communities/999/join")
    assert response.status_code == 404
    assert response.json().get("detail") == "Community not found"


def test_leave_community(authorized_client, test_community):
    community_id = test_community[0].id
    # Join first
    authorized_client.post(f"/communities/{community_id}/join")
    response = authorized_client.post(f"/communities/{community_id}/leave")
    assert response.status_code == 200
    assert response.json().get("message") == "Left the community successfully"


def test_leave_non_existent_community(authorized_client):
    response = authorized_client.post("/communities/999/leave")
    assert response.status_code == 404
    assert response.json().get("detail") == "Community not found"


def test_leave_community_not_joined(authorized_client, test_community):
    community_id = test_community[0].id
    response = authorized_client.post(f"/communities/{community_id}/leave")
    assert response.status_code == 400
    assert response.json().get("detail") == "User is not a member of this community"


def test_multiple_membership(authorized_client, test_community):
    community_id = test_community[0].id
    response = authorized_client.post(f"/communities/{community_id}/join")
    assert response.status_code == 200
    response = authorized_client.post(f"/communities/{community_id}/join")
    assert response.status_code == 400
    assert response.json().get("detail") == "User is already a member of this community"


def test_community_details(authorized_client, test_community):
    community_id = test_community[0].id
    response = authorized_client.get(f"/communities/{community_id}")
    assert response.status_code == 200
    community = response.json()
    assert community["community"]["id"] == community_id


def test_community_without_description(authorized_client):
    response = authorized_client.post(
        "/communities/", json={"name": "Community Without Description"}
    )
    assert response.status_code == 201
    community = response.json()["community"]
    assert community["name"] == "Community Without Description"
    assert community["description"] is None
