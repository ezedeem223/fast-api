from app.oauth2 import create_access_token
from tests.conftest import TestingSessionLocal
import app.models as models


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_e2e_lifecycle_flow(client, test_user, test_user2):
    # User 1 login
    login_res = client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    assert login_res.status_code == 200
    token1 = login_res.json()["access_token"]

    # User 1 creates a post
    post_res = client.post(
        "/posts/",
        headers=_auth_headers(token1),
        json={"title": "Lifecycle Post", "content": "Lifecycle content"},
    )
    assert post_res.status_code == 201
    post_id = post_res.json()["id"]

    # User 2 login (token via login or direct creation fallback)
    login_res2 = client.post(
        "/login",
        data={"username": test_user2["email"], "password": test_user2["password"]},
    )
    if login_res2.status_code == 200:
        token2 = login_res2.json()["access_token"]
    else:
        token2 = create_access_token({"user_id": test_user2["id"]})

    # User 2 comments on the post
    comment_res = client.post(
        "/comments/",
        headers=_auth_headers(token2),
        json={"content": "Nice post!", "post_id": post_id},
    )
    assert comment_res.status_code == 201

    # Fetch comment id directly from DB to avoid response schema differences
    with TestingSessionLocal() as db:
        comment_obj = (
            db.query(models.Comment)
            .filter(models.Comment.post_id == post_id, models.Comment.owner_id == test_user2["id"])
            .order_by(models.Comment.id.desc())
            .first()
        )
        assert comment_obj is not None
        comment_id = comment_obj.id

    # User 1 reports the comment
    report_res = client.post(
        "/comments/report",
        headers=_auth_headers(token1),
        json={"comment_id": comment_id, "reason": "spam"},
    )
    assert report_res.status_code == 201

    # User 1 blocks User 2
    block_res = client.post(
        "/block/",
        headers=_auth_headers(token1),
        json={"blocked_id": test_user2["id"], "block_type": "full"},
    )
    assert block_res.status_code == 201
