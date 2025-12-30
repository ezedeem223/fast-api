import app.models as models
from app.oauth2 import create_access_token
from tests.conftest import TestingSessionLocal


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_cannot_update_other_users_comment(client, test_user, test_user2):
    # Seed a post/comment owned by user1
    with TestingSessionLocal() as db:
        post = models.Post(
            title="Protected Post", content="body", owner_id=test_user["id"]
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        comment = models.Comment(
            content="user1 comment", owner_id=test_user["id"], post_id=post.id
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        comment_id = comment.id

    token_other = create_access_token({"user_id": test_user2["id"]})
    res = client.put(
        f"/comments/{comment_id}",
        headers=_auth(token_other),
        json={"content": "attempted edit"},
    )
    assert res.status_code == 403


def test_non_moderator_cannot_view_block_appeals(client, test_user):
    token = create_access_token({"user_id": test_user["id"]})
    res = client.get("/block/appeals", headers=_auth(token))
    assert res.status_code in (401, 403, 422)
