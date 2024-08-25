import pytest
from app import models


@pytest.fixture()
def test_community(test_user, session):
    new_community = models.Community(
        name="test_community",
        description="A community for testing",
        owner_id=test_user["id"],
    )
    session.add(new_community)
    session.commit()
    return new_community


def test_create_community(authorized_client, test_user):
    res = authorized_client.post(
        "/communities/",
        json={"name": "new_community", "description": "New community for testing"},
    )
    assert res.status_code == 201
    assert res.json()["name"] == "new_community"
    assert res.json()["description"] == "New community for testing"
    assert res.json()["owner_id"] == test_user["id"]


def test_get_communities(authorized_client, test_community):
    res = authorized_client.get("/communities/")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == test_community.name


def test_join_community(authorized_client, test_user2, test_community, session):
    res = authorized_client.post(f"/communities/{test_community.id}/join")
    assert res.status_code == 200

    community_members = (
        session.query(models.Community)
        .filter(models.Community.id == test_community.id)
        .first()
        .members
    )
    assert test_user2["id"] in [member.id for member in community_members]


def test_leave_community(authorized_client, test_user2, test_community, session):
    # Join first
    authorized_client.post(f"/communities/{test_community.id}/join")

    # Then leave
    res = authorized_client.post(f"/communities/{test_community.id}/leave")
    assert res.status_code == 200

    community_members = (
        session.query(models.Community)
        .filter(models.Community.id == test_community.id)
        .first()
        .members
    )
    assert test_user2["id"] not in [member.id for member in community_members]


def test_create_duplicate_community(authorized_client, test_community):
    res = authorized_client.post(
        "/communities/",
        json={
            "name": test_community.name,
            "description": "Another community with the same name",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Community already exists"


def test_join_non_existent_community(authorized_client):
    res = authorized_client.post("/communities/9999/join")
    assert res.status_code == 404
    assert res.json()["detail"] == "Community not found"


def test_leave_non_existent_community(authorized_client):
    res = authorized_client.post("/communities/9999/leave")
    assert res.status_code == 404
    assert res.json()["detail"] == "Community not found"


def test_cannot_join_same_community_twice(authorized_client, test_community, session):
    # أول محاولة انضمام
    res = authorized_client.post(f"/communities/{test_community.id}/join")
    assert res.status_code == 200

    # محاولة انضمام ثانية
    res = authorized_client.post(f"/communities/{test_community.id}/join")
    assert res.status_code == 400
    assert res.json()["detail"] == "User is already a member of this community"


def test_unverified_user_cannot_create_community(client, test_user):
    # محاولة إنشاء مجتمع من قبل مستخدم غير موثق
    res = client.post(
        "/communities/",
        json={"name": "unverified_community", "description": "Test community"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "User is not verified."


def test_owner_cannot_leave_own_community(authorized_client, test_community, session):
    # محاولة مالك المجتمع مغادرة المجتمع
    res = authorized_client.post(f"/communities/{test_community.id}/leave")
    assert res.status_code == 400
    assert res.json()["detail"] == "Owner cannot leave their own community"
