import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app import schemas, models


@pytest.fixture(scope="function")
def authorized_client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.mark.parametrize(
    "community_data, expected_status_code, expected_response",
    [
        (
            {"name": "Community 1", "description": "Test Community"},
            201,
            {"community": {"name": "Community 1", "description": "Test Community"}},
        ),
        (
            {"name": "Community 1"},
            400,
            {"detail": "Community already exists"},
        ),  # Duplicate name scenario
    ],
)
def test_create_community(
    authorized_client, community_data, expected_status_code, expected_response
):
    response = authorized_client.post("/communities/", json=community_data)
    assert response.status_code == expected_status_code
    assert response.json() == expected_response


@pytest.mark.parametrize(
    "community_data, expected_status_code, expected_response",
    [
        (
            {"name": "Community 1", "description": "Test Community"},
            201,
            {"community": {"name": "Community 1", "description": "Test Community"}},
        ),
        (
            {"name": "Community 1"},
            400,
            {"detail": "Community already exists"},
        ),  # Duplicate name scenario
    ],
)
def test_create_existing_community(
    authorized_client, community_data, expected_status_code, expected_response
):
    authorized_client.post(
        "/communities/", json=community_data
    )  # Create initial community
    response = authorized_client.post(
        "/communities/", json=community_data
    )  # Try to create duplicate
    assert response.status_code == expected_status_code
    assert response.json() == expected_response


def test_get_communities(authorized_client, test_community):
    response = authorized_client.get("/communities/")
    assert response.status_code == 200
    communities = response.json()
    assert isinstance(communities, list)
    assert len(communities) > 0


def test_join_community(authorized_client, test_community):
    response = authorized_client.post(f"/communities/{test_community['id']}/join")
    assert response.status_code == 200
    assert response.json() == {"message": "Joined the community"}


def test_join_non_existent_community(authorized_client):
    response = authorized_client.post("/communities/999/join")
    assert response.status_code == 404
    assert response.json() == {"detail": "Community not found"}


def test_leave_community(authorized_client, test_community):
    authorized_client.post(
        f"/communities/{test_community['id']}/join"
    )  # Ensure user is in the community
    response = authorized_client.post(f"/communities/{test_community['id']}/leave")
    assert response.status_code == 200
    assert response.json() == {"message": "Left the community"}


def test_leave_non_existent_community(authorized_client):
    response = authorized_client.post("/communities/999/leave")
    assert response.status_code == 404
    assert response.json() == {"detail": "Community not found"}


def test_leave_community_not_joined(authorized_client, test_community):
    response = authorized_client.post(f"/communities/{test_community['id']}/leave")
    assert response.status_code == 400
    assert response.json() == {"detail": "You are not a member of this community"}


def test_multiple_membership(authorized_client, test_community):
    # Join community twice
    response = authorized_client.post(f"/communities/{test_community['id']}/join")
    assert response.status_code == 200
    response = authorized_client.post(f"/communities/{test_community['id']}/join")
    assert response.status_code == 400
    assert response.json() == {"detail": "Already a member of this community"}


def test_community_details(authorized_client, test_community):
    response = authorized_client.get(f"/communities/{test_community['id']}")
    assert response.status_code == 200
    community = response.json()
    assert community["community"]["id"] == test_community["id"]
    assert community["community"]["name"] == test_community["name"]


def test_community_without_description(authorized_client):
    response = authorized_client.post(
        "/communities/", json={"name": "Community Without Description"}
    )
    assert response.status_code == 201
    community = response.json()["community"]
    assert community["name"] == "Community Without Description"
    assert community["description"] is None
