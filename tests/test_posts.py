import pytest
from app import schemas, models
from app.core.config import settings
from datetime import datetime


def test_root(client):
    res = client.get("/")
    assert res.json().get("message") == "Hello, World!"
    assert res.status_code == 200


def test_create_user(client):
    res = client.post(
        "/users/", json={"email": "test@example.com", "password": "password123"}
    )
    new_user = schemas.UserOut(**res.json())
    assert new_user.email == "test@example.com"
    assert res.status_code == 201


def test_login_user(client, test_user):
    res = client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    login_res = schemas.Token(**res.json())
    assert login_res.token_type == "bearer"
    assert res.status_code == 200


def test_incorrect_login(client, test_user):
    res = client.post(
        "/login", data={"username": test_user["email"], "password": "wrongpassword"}
    )
    assert res.status_code == 403
    assert res.json().get("detail") == "Invalid Credentials"


def test_get_all_posts(authorized_client, test_posts):
    res = authorized_client.get("/posts/")
    assert len(res.json()) == len(test_posts)
    assert res.status_code == 200


def test_get_one_post(authorized_client, test_posts):
    res = authorized_client.get(f"/posts/{test_posts[0].id}")
    post = schemas.PostOut(**res.json())
    assert post.id == test_posts[0].id
    assert post.content == test_posts[0].content
    assert post.title == test_posts[0].title


def test_get_one_post_not_exist(authorized_client, test_posts):
    res = authorized_client.get(f"/posts/88888")
    assert res.status_code == 404


def test_unauthorized_user_get_all_posts(client, test_posts):
    res = client.get("/posts/")
    assert res.status_code == 401


def test_unauthorized_user_get_one_post(client, test_posts):
    res = client.get(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_create_post(authorized_client, test_user, session):
    # Verify the user
    session.query(models.User).filter(models.User.id == test_user["id"]).update(
        {"is_verified": True}
    )
    session.commit()

    res = authorized_client.post(
        "/posts/",
        json={"title": "Test title", "content": "Test content", "published": True},
    )
    assert res.status_code == 201
    created_post = schemas.Post(**res.json())
    assert created_post.title == "Test title"
    assert created_post.content == "Test content"
    assert created_post.published == True
    assert created_post.owner_id == test_user["id"]
    assert isinstance(created_post.created_at, datetime)
    assert hasattr(created_post, "id")
    assert hasattr(created_post, "owner")


def test_create_post_default_published_true(authorized_client, test_user, session):
    # Verify the user
    session.query(models.User).filter(models.User.id == test_user["id"]).update(
        {"is_verified": True}
    )
    session.commit()

    res = authorized_client.post(
        "/posts/", json={"title": "Test title", "content": "Test content"}
    )
    assert res.status_code == 201
    created_post = schemas.Post(**res.json())
    assert created_post.title == "Test title"
    assert created_post.content == "Test content"
    assert created_post.published == True
    assert created_post.owner_id == test_user["id"]
    assert isinstance(created_post.created_at, datetime)
    assert hasattr(created_post, "id")
    assert hasattr(created_post, "owner")


def test_unauthorized_user_create_post(client, test_user, test_posts):
    res = client.post(
        "/posts/", json={"title": "Test title", "content": "Test content"}
    )
    assert res.status_code == 401


def test_unauthorized_user_delete_Post(client, test_user, test_posts):
    res = client.delete(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_delete_post_success(authorized_client, test_user, test_posts):
    res = authorized_client.delete(f"/posts/{test_posts[0].id}")
    assert res.status_code == 204


def test_delete_post_non_exist(authorized_client, test_user, test_posts):
    res = authorized_client.delete(f"/posts/8000000")
    assert res.status_code == 404


def test_delete_other_user_post(authorized_client, test_user, test_posts):
    res = authorized_client.delete(f"/posts/{test_posts[3].id}")
    assert res.status_code == 403


def test_update_post(authorized_client, test_user, test_posts):
    data = {
        "title": "updated title",
        "content": "updated content",
        "id": test_posts[0].id,
    }
    res = authorized_client.put(f"/posts/{test_posts[0].id}", json=data)
    updated_post = schemas.Post(**res.json())
    assert res.status_code == 200
    assert updated_post.title == data["title"]
    assert updated_post.content == data["content"]


def test_update_other_user_post(authorized_client, test_user, test_posts):
    data = {
        "title": "updated title",
        "content": "updated content",
        "id": test_posts[3].id,
    }
    res = authorized_client.put(f"/posts/{test_posts[3].id}", json=data)
    assert res.status_code == 403


def test_unauthorized_user_update_post(client, test_user, test_posts):
    res = client.put(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401


def test_update_post_non_exist(authorized_client, test_user, test_posts):
    data = {
        "title": "updated title",
        "content": "updated content",
        "id": test_posts[0].id,
    }
    res = authorized_client.put(f"/posts/8000000", json=data)
    assert res.status_code == 404
