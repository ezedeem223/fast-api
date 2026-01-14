"""Test module for test posts."""
from datetime import datetime

from app import models, schemas


def test_root(client):
    """Test case for test root."""
    res = client.get("/")
    assert res.json().get("message") == "Hello, World!"
    assert res.status_code == 200


def test_get_all_posts(authorized_client, test_posts):
    """Test case for test get all posts."""
    res = authorized_client.get("/posts/")
    assert len(res.json()) == len(test_posts)
    assert res.status_code == 200


def test_get_one_post(authorized_client, test_posts):
    """Test case for test get one post."""
    res = authorized_client.get(f"/posts/{test_posts[0].id}")
    post = schemas.PostOut(**res.json())
    assert post.id == test_posts[0].id
    assert post.content == test_posts[0].content
    assert post.title == test_posts[0].title


def test_get_one_post_not_exist(authorized_client, test_posts):
    """Test case for test get one post not exist."""
    res = authorized_client.get("/posts/88888")
    assert res.status_code == 404
    assert "was not found" in res.json()["detail"]


def test_unauthorized_user_get_all_posts(client, test_posts):
    """Test case for test unauthorized user get all posts."""
    res = client.get("/posts/")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_unauthorized_user_get_one_post(client, test_posts):
    """Test case for test unauthorized user get one post."""
    res = client.get(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_create_post(authorized_client, test_user, session):
    # Verify the user
    """Test case for test create post."""
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
    assert created_post.published
    assert created_post.owner_id == test_user["id"]
    assert isinstance(created_post.created_at, datetime)
    assert hasattr(created_post, "id")
    assert hasattr(created_post, "owner")


def test_create_post_default_published_true(authorized_client, test_user, session):
    # Verify the user
    """Test case for test create post default published true."""
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
    assert created_post.published
    assert created_post.owner_id == test_user["id"]
    assert isinstance(created_post.created_at, datetime)
    assert hasattr(created_post, "id")
    assert hasattr(created_post, "owner")


def test_unauthorized_user_create_post(client, session, test_user, test_posts):
    """Test case for test unauthorized user create post."""
    before = session.query(models.Post).count()
    res = client.post(
        "/posts/", json={"title": "Test title", "content": "Test content"}
    )
    assert res.status_code == 401
    after = session.query(models.Post).count()
    assert after == before


def test_unauthorized_user_delete_Post(client, test_user, test_posts):
    """Test case for test unauthorized user delete Post."""
    res = client.delete(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_delete_post_success(authorized_client, test_user, test_posts):
    """Test case for test delete post success."""
    res = authorized_client.delete(f"/posts/{test_posts[0].id}")
    assert res.status_code == 204
    assert res.text == ""


def test_delete_post_non_exist(authorized_client, test_user, test_posts):
    """Test case for test delete post non exist."""
    res = authorized_client.delete("/posts/8000000")
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"]


def test_update_post(authorized_client, test_user, test_posts):
    """Test case for test update post."""
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


def test_unauthorized_user_update_post(client, test_user, test_posts):
    """Test case for test unauthorized user update post."""
    res = client.put(f"/posts/{test_posts[0].id}")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_update_post_non_exist(authorized_client, test_user, test_posts):
    """Test case for test update post non exist."""
    data = {
        "title": "updated title",
        "content": "updated content",
        "id": test_posts[0].id,
    }
    res = authorized_client.put("/posts/8000000", json=data)
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"]
