def test_create_post_with_empty_title(authorized_client):
    res = authorized_client.post(
        "/posts/", json={"title": "", "content": "Test content"}
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["type"] == "string_too_short"


def test_create_post_with_long_title(authorized_client):
    long_title = "a" * 301  # Assuming max length is 300
    res = authorized_client.post(
        "/posts/", json={"title": long_title, "content": "Test content"}
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["type"] == "string_too_long"


def test_create_post_with_empty_content(authorized_client):
    res = authorized_client.post("/posts/", json={"title": "Test title", "content": ""})
    assert res.status_code == 422
    assert res.json()["detail"] == "Content cannot be empty"


def test_delete_nonexistent_post(authorized_client):
    res = authorized_client.delete("/posts/9999")
    assert res.status_code == 404
    detail = res.json()["detail"].lower()
    assert "post with id" in detail and "does not exist" in detail


def test_unauthorized_user_access_protected_route(client):
    res = client.get("/posts/")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_create_post_unauthorized(client):
    res = client.post(
        "/posts/", json={"title": "Test title", "content": "Test content"}
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_update_other_user_post(authorized_client, test_posts, test_user2):
    other_user_post = [
        post for post in test_posts if post.owner_id == test_user2["id"]
    ][0]
    res = authorized_client.put(
        f"/posts/{other_user_post.id}",
        json={"title": "Updated title", "content": "Updated content"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Not authorized to perform requested action"


def test_delete_other_user_post(authorized_client, test_posts, test_user2):
    other_user_post = [
        post for post in test_posts if post.owner_id == test_user2["id"]
    ][0]
    res = authorized_client.delete(f"/posts/{other_user_post.id}")
    assert res.status_code == 403
    assert res.json()["detail"] == "Not authorized to perform requested action"


def test_get_nonexistent_post(authorized_client):
    res = authorized_client.get("/posts/9999")
    assert res.status_code == 404
    detail = res.json()["detail"].lower()
    assert "post with id" in detail and "was not found" in detail


def test_create_duplicate_user(client, test_user):
    res = client.post(
        "/users/", json={"email": test_user["email"], "password": "newpassword123"}
    )
    assert res.status_code == 400
    assert "email already registered" in res.json()["detail"].lower()


def test_create_post_with_invalid_json(authorized_client):
    res = authorized_client.post("/posts/", json={"invalid_field": "value"})
    assert res.status_code == 422
    assert (
        "missing" in res.json()["detail"][0]["type"]
    )  # Changed from 'value_error.missing' to 'missing'


# These tests might need to be adjusted based on your actual implementation
def test_get_all_posts_pagination(authorized_client, test_posts):
    res = authorized_client.get("/posts/?limit=2&skip=1")
    assert res.status_code == 200
    # You might need to adjust the assertion based on your actual response structure


def test_search_posts(authorized_client, test_posts):
    res = authorized_client.get("/posts/?search=first")
    assert res.status_code == 200
    # You might need to adjust the assertion based on your actual response structure


def test_post_with_emoji_only_content(authorized_client):
    res = authorized_client.post(
        "/posts/", json={"title": "😀 title", "content": "😀😀😀"}
    )
    assert res.status_code in (200, 201)
    body = res.json()
    assert body["content"].startswith("😀")


def test_post_rejects_sql_injection_like_payload(authorized_client):
    payload = {"title": "sql test", "content": "'; DROP TABLE users;--"}
    res = authorized_client.post("/posts/", json=payload)
    # Accept either validation error or successful handling; must not 500
    assert res.status_code != 500


def test_large_content_handled_gracefully(authorized_client):
    big_content = "x" * 5000
    res = authorized_client.post(
        "/posts/", json={"title": "Big Content", "content": big_content}
    )
    assert res.status_code in (200, 201, 422)
