import pytest

from app import models


def test_export_includes_posts_comments_and_identities(
    authorized_client, session, test_post, test_user, test_user2
):
    # create a comment
    comment = models.Comment(
        content="test comment", owner_id=test_user["id"], post_id=test_post["id"]
    )
    session.add(comment)
    session.commit()

    # link identity to second user
    link_res = authorized_client.post(
        "/users/me/identities",
        json={"linked_user_id": test_user2["id"], "relationship_type": "alias"},
    )
    assert link_res.status_code == 201

    res = authorized_client.get("/users/me/export")
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == test_user["email"]
    assert len(data["posts"]) >= 1
    assert len(data["comments"]) >= 1
    assert any(
        identity["linked_user_id"] == test_user2["id"] for identity in data["identities"]
    )


def test_delete_account_removes_user_and_content(
    authorized_client, session, test_post, test_user
):
    res = authorized_client.delete("/users/me")
    assert res.status_code == 204

    session.expire_all()
    user = session.query(models.User).filter(models.User.id == test_user["id"]).first()
    post = session.query(models.Post).filter(models.Post.id == test_post["id"]).first()
    assert user is None
    assert post is None
