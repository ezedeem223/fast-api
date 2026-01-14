"""Test module for test security permissions."""
import app.models as models
from app.oauth2 import create_access_token
from tests.conftest import TestingSessionLocal


def _auth(token: str) -> dict:
    """Helper for  auth."""
    return {"Authorization": f"Bearer {token}"}


def test_cannot_update_other_users_comment(client, test_user, test_user2):
    # Seed a post/comment owned by user1
    """Test case for test cannot update other users comment."""
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
    assert res.json()["detail"] == "Not authorized to edit this comment"


def test_non_moderator_cannot_view_block_appeals(client, test_user):
    """Test case for test non moderator cannot view block appeals."""
    token = create_access_token({"user_id": test_user["id"]})
    res = client.get("/block/appeals", headers=_auth(token))
    assert res.status_code in (401, 403, 422)
    if res.status_code == 403:
        assert res.json()["detail"] == "Only moderators can view appeals"
    elif res.status_code == 401:
        assert res.json()["detail"] == "Not authenticated"
