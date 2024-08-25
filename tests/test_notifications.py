import pytest
from app import models
from app.notifications import manager  # استيراد مدير الاتصالات للإشعارات الفورية


@pytest.fixture
def test_post(authorized_client, test_user, session):
    post_data = {"title": "Test Post", "content": "Test Content", "published": True}
    response = authorized_client.post("/posts/", json=post_data)
    assert response.status_code == 201
    post = response.json()
    session.add(models.Post(id=post["id"], owner_id=test_user["id"], **post_data))
    session.commit()
    return post


@pytest.fixture
def test_comment(authorized_client, test_user, test_post, session):
    comment_data = {"content": "Test Comment", "post_id": test_post["id"]}
    response = authorized_client.post("/comments/", json=comment_data)
    assert response.status_code == 201
    comment = response.json()
    session.add(
        models.Comment(
            id=comment["id"],
            owner_id=test_user["id"],
            post_id=test_post["id"],
            content="Test Comment",
        )
    )
    session.commit()
    return comment


def test_notification_on_new_post(authorized_client, test_user):
    response = authorized_client.post(
        "/posts/", json={"title": "New Post", "content": "New Content"}
    )
    assert response.status_code == 201
    # تحقق من أن الإشعار تم إرساله بنجاح
    background_tasks = response.json().get("background_tasks")
    assert background_tasks is not None
    notification_sent = manager.get_notification_status()
    assert notification_sent == f"New post created: New Post"


def test_notification_on_new_comment(authorized_client, test_post, test_user):
    response = authorized_client.post(
        "/comments/", json={"post_id": test_post["id"], "content": "New Comment"}
    )
    assert response.status_code == 201
    # تحقق من أن الإشعار تم إرساله بنجاح
    background_tasks = response.json().get("background_tasks")
    assert background_tasks is not None
    notification_sent = manager.get_notification_status()
    assert (
        notification_sent
        == f"User {test_user['id']} has commented on post {test_post['id']}."
    )


def test_notification_on_new_vote(authorized_client, test_post, test_user):
    response = authorized_client.post(
        "/vote/", json={"post_id": test_post["id"], "dir": 1}
    )
    assert response.status_code == 201
    # تحقق من أن الإشعار تم إرساله بنجاح
    background_tasks = response.json().get("background_tasks")
    assert background_tasks is not None
    notification_sent = manager.get_notification_status()
    assert (
        notification_sent
        == f"User {test_user['id']} has voted on post {test_post['id']}."
    )


def test_notification_on_new_follow(authorized_client, test_user, test_user2):
    response = authorized_client.post(f"/follow/{test_user2['id']}")
    assert response.status_code == 201
    # تحقق من أن الإشعار تم إرساله بنجاح
    background_tasks = response.json().get("background_tasks")
    assert background_tasks is not None
    notification_sent = manager.get_notification_status()
    assert (
        notification_sent
        == f"User {test_user['id']} has followed User {test_user2['id']}."
    )
