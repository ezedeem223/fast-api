import pytest
from app import models


def test_follow_user(authorized_client, test_user2, session):
    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 201
    assert response.json()["message"] == "Successfully followed user"

    follow = (
        session.query(models.Follow).filter_by(follower_id=test_user2["id"]).first()
    )
    assert follow is not None


def test_unfollow_user(authorized_client, test_user2, session):
    # أولاً نتأكد من أن المستخدم يتابع المستخدم الثاني
    authorized_client.post(f"/follow/{test_user2['id']}")

    # الآن نلغي المتابعة
    response = authorized_client.delete(f"/follow/{test_user2['id']}")
    assert response.status_code == 204

    follow = (
        session.query(models.Follow).filter_by(follower_id=test_user2["id"]).first()
    )
    assert follow is None


def test_cannot_follow_self(authorized_client, test_user):
    response = authorized_client.post(f"/follow/{test_user['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot follow yourself"


def test_cannot_follow_twice(authorized_client, test_user2):
    # أول متابعة
    authorized_client.post(f"/follow/{test_user2['id']}")
    # محاولة متابعة نفس المستخدم مرة أخرى
    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "You already follow this user"
