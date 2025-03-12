import pytest
from fastapi import BackgroundTasks
from app import models
from app.notifications import (
    manager,
    send_email_notification,
    schedule_email_notification,
)
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_background_tasks():
    return MagicMock(spec=BackgroundTasks)


@pytest.fixture
def mock_notification_manager():
    with patch("app.notifications.manager") as mock:
        yield mock


@pytest.fixture
def mock_send_email():
    with patch("app.notifications.send_email_notification") as mock:
        yield mock


def test_notification_on_new_post(
    authorized_client,
    test_user,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    post_data = {"title": "New Post", "content": "New Content", "published": True}

    with patch("app.routers.post.BackgroundTasks", return_value=mock_background_tasks):
        response = authorized_client.post("/posts/", json=post_data)

    assert response.status_code == 201

    mock_notification_manager.broadcast.assert_called_with(
        f"New post created: New Post"
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_user["email"],
        subject="New Post Created",
        body=f"Your post '{post_data['title']}' has been created successfully.",
    )


def test_notification_on_new_comment(
    authorized_client,
    test_user,
    test_posts,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    comment_data = {"content": "Test Comment", "post_id": test_posts[0].id}

    with patch(
        "app.routers.comment.BackgroundTasks", return_value=mock_background_tasks
    ):
        response = authorized_client.post("/comments/", json=comment_data)

    assert response.status_code == 201

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has commented on post {test_posts[0].id}."
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_posts[0].owner.email,
        subject="New Comment on Your Post",
        body=f"A new comment has been added to your post '{test_posts[0].title}'.",
    )


def test_notification_on_new_vote(
    authorized_client,
    test_user,
    test_posts,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    vote_data = {"post_id": test_posts[0].id, "dir": 1}

    with patch("app.routers.vote.BackgroundTasks", return_value=mock_background_tasks):
        response = authorized_client.post("/vote/", json=vote_data)

    assert response.status_code == 201

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has voted on post {test_posts[0].id}."
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_posts[0].owner.email,
        subject="New Vote on Your Post",
        body=f"Your post '{test_posts[0].title}' has received a new vote.",
    )


def test_notification_on_new_follow(
    authorized_client,
    test_user,
    test_user2,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
):
    with patch("app.routers.user.BackgroundTasks", return_value=mock_background_tasks):
        response = authorized_client.post(f"/follow/{test_user2['id']}")

    assert response.status_code == 201

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has followed User {test_user2['id']}."
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_user2["email"],
        subject="New Follower",
        body=f"User {test_user['email']} is now following you.",
    )


@pytest.mark.asyncio
async def test_real_time_notification(client, test_user):
    websocket_url = f"/ws/{test_user['id']}"
    with client.websocket_connect(websocket_url) as websocket:
        await websocket.send_text("Test message")
        response = await websocket.receive_text()
        assert f"User {test_user['id']} says: Test message" in response


def test_email_notification_scheduled(
    authorized_client, test_user, mock_background_tasks
):
    with patch("app.notifications.schedule_email_notification") as mock_schedule_email:
        with patch(
            "app.routers.post.BackgroundTasks", return_value=mock_background_tasks
        ):
            post_data = {
                "title": "Email Test Post",
                "content": "Test Content",
                "published": True,
            }
            response = authorized_client.post("/posts/", json=post_data)

    assert response.status_code == 201

    mock_schedule_email.assert_called_with(
        mock_background_tasks,
        to=test_user["email"],
        subject="New Post Created",
        body=f"Your post '{post_data['title']}' has been created successfully.",
    )


def test_notification_on_message(
    authorized_client,
    test_user,
    test_user2,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
):
    message_data = {"content": "Hello!", "recipient_id": test_user2["id"]}

    with patch(
        "app.routers.message.BackgroundTasks", return_value=mock_background_tasks
    ):
        response = authorized_client.post("/message/", json=message_data)

    assert response.status_code == 201

    mock_notification_manager.send_personal_message.assert_called_with(
        f"New message from {test_user['email']}: Hello!", f"/ws/{test_user2['id']}"
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_user2["email"],
        subject="New Message Received",
        body=f"You have received a new message from {test_user['email']}.",
    )


def test_notification_on_community_join(
    authorized_client,
    test_user,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    community_data = {"name": "Test Community", "description": "A test community"}

    with patch(
        "app.routers.community.BackgroundTasks", return_value=mock_background_tasks
    ):
        community_response = authorized_client.post(
            "/communities/", json=community_data
        )

    assert community_response.status_code == 201
    community_id = community_response.json()["id"]

    with patch(
        "app.routers.community.BackgroundTasks", return_value=mock_background_tasks
    ):
        join_response = authorized_client.post(f"/communities/{community_id}/join")

    assert join_response.status_code == 200

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has joined the community 'Test Community'."
    )

    mock_background_tasks.add_task.assert_called_with(
        send_email_notification,
        to=test_user["email"],
        subject="New Member in Your Community",
        body=f"A new member has joined your community 'Test Community'.",
    )


# Add more notification tests as needed, for example:
# - Notifications for post updates
# - Notifications for comment replies
# - Notifications for community events
# - Notifications for admin actions
# لاحقا
