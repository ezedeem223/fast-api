"""Test module for test notifications."""
from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app import models
from app.modules.community import CommunityMember
from app.modules.notifications import models as notification_models
from app.notifications import send_real_time_notification
from fastapi import BackgroundTasks


@pytest.fixture
def mock_background_tasks():
    """Pytest fixture for mock_background_tasks."""
    return MagicMock(spec=BackgroundTasks)


@pytest.fixture
def mock_notification_manager():
    """Pytest fixture for mock_notification_manager."""
    with patch("app.notifications.manager") as mock:
        mock.send_personal_message = AsyncMock()
        yield mock


@pytest.fixture
def mock_send_email():
    """Pytest fixture for mock_send_email."""
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
    """Test case for test notification on new post."""
    post_data = {"title": "New Post", "content": "New Content", "published": True}

    with (
        patch("app.routers.post.queue_email_notification") as mock_queue_email,
        patch("app.routers.post.schedule_email_notification") as mock_schedule_email,
    ):
        response = authorized_client.post("/posts/", json=post_data)

    assert response.status_code == 201
    assert response.json()["title"] == post_data["title"]

    mock_notification_manager.broadcast.assert_called_with("New post created: New Post")

    expected_kwargs = dict(
        to=test_user["email"],
        subject="New Post Created",
        body=f"Your post '{post_data['title']}' has been created successfully.",
    )
    mock_queue_email.assert_called_with(ANY, **expected_kwargs)
    mock_schedule_email.assert_called_with(ANY, **expected_kwargs)


def test_notification_on_new_comment(
    authorized_client,
    test_user,
    test_posts,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    """Test case for test notification on new comment."""
    comment_data = {"content": "Test Comment", "post_id": test_posts[0].id}

    with (
        patch("app.routers.comment.queue_email_notification") as mock_queue_email,
        patch("app.routers.comment.schedule_email_notification") as mock_schedule_email,
    ):
        response = authorized_client.post("/comments/", json=comment_data)

    assert response.status_code == 201
    payload = response.json()
    assert payload["reported_count"] == 0
    assert payload["is_flagged"] is False

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has commented on post {test_posts[0].id}."
    )

    expected_kwargs = dict(
        to=test_posts[0].owner.email,
        subject="New Comment on Your Post",
        body=f"A new comment has been added to your post '{test_posts[0].title}'.",
    )
    mock_queue_email.assert_called_with(ANY, **expected_kwargs)
    mock_schedule_email.assert_called_with(ANY, **expected_kwargs)


def test_notification_on_new_vote(
    authorized_client,
    test_user,
    test_posts,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    """Test case for test notification on new vote."""
    vote_data = {"post_id": test_posts[0].id, "reaction_type": "like"}

    with (
        patch("app.routers.vote.queue_email_notification") as mock_queue_email,
        patch("app.routers.vote.schedule_email_notification") as mock_schedule_email,
    ):
        response = authorized_client.post("/vote/", json=vote_data)

    assert response.status_code == 201
    payload = response.json()
    assert "message" in payload
    assert vote_data["reaction_type"] in payload["message"]

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has voted on post {vote_data['post_id']}."
    )

    post = session.get(models.Post, vote_data["post_id"])
    expected_kwargs = dict(
        to=post.owner.email,
        subject="New Vote on Your Post",
        body=f"Your post '{post.title}' has received a new vote.",
    )
    mock_queue_email.assert_called_with(ANY, **expected_kwargs)
    mock_schedule_email.assert_called_with(ANY, **expected_kwargs)


def test_notification_on_new_follow(
    authorized_client,
    test_user,
    test_user2,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
):
    """Test case for test notification on new follow."""
    with (
        patch("app.routers.follow.queue_email_notification") as mock_queue_email,
        patch("app.routers.follow.schedule_email_notification") as mock_schedule_email,
    ):
        response = authorized_client.post(f"/follow/{test_user2['id']}")

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully followed user"

    mock_notification_manager.broadcast.assert_called_with(
        f"User {test_user['id']} has followed User {test_user2['id']}."
    )

    expected_kwargs = dict(
        to=test_user2["email"],
        subject="New Follower",
        body=f"User {test_user['email']} is now following you.",
    )
    mock_queue_email.assert_called_with(ANY, **expected_kwargs)
    mock_schedule_email.assert_called_with(ANY, **expected_kwargs)


@pytest.mark.asyncio
async def test_real_time_notification(mock_notification_manager):
    """Test case for test real time notification."""
    await send_real_time_notification(1, "Test message")
    mock_notification_manager.send_personal_message.assert_called_with(
        {"message": "Test message", "type": "simple_notification"}, 1
    )


def test_email_notification_scheduled(authorized_client, test_user):
    """Test case for test email notification scheduled."""
    post_data = {
        "title": "Email Test Post",
        "content": "Test Content",
        "published": True,
    }

    with patch("app.routers.post.schedule_email_notification") as mock_schedule_email:
        response = authorized_client.post("/posts/", json=post_data)

    assert response.status_code == 201
    assert response.json()["title"] == post_data["title"]

    mock_schedule_email.assert_called_with(
        ANY,
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
    """Test case for test notification on message."""
    message_data = {"content": "Hello!", "recipient_id": test_user2["id"]}

    with (
        patch("app.routers.message.queue_email_notification") as mock_queue_email,
        patch("app.routers.message.schedule_email_notification") as mock_schedule_email,
    ):
        response = authorized_client.post("/message/", json=message_data)

    assert response.status_code == 201
    assert response.json()["content"] == message_data["content"]

    mock_notification_manager.send_personal_message.assert_called_with(
        f"New message from {test_user['email']}: Hello!", f"/ws/{test_user2['id']}"
    )

    expected_kwargs = dict(
        to=test_user2["email"],
        subject="New Message Received",
        body=f"You have received a new message from {test_user['email']}.",
    )
    mock_queue_email.assert_called_with(ANY, **expected_kwargs)
    mock_schedule_email.assert_called_with(ANY, **expected_kwargs)


def test_notification_on_community_join(
    authorized_client,
    client,
    test_user,
    test_user2,
    mock_background_tasks,
    mock_notification_manager,
    mock_send_email,
    session,
):
    """Test case for test notification on community join."""
    # Arrange: create a community and log in as a second user.
    community_data = {"name": "Test Community", "description": "A test community"}

    with patch(
        "app.routers.community.BackgroundTasks", return_value=mock_background_tasks
    ):
        community_response = authorized_client.post(
            "/communities/", json=community_data
        )

    assert community_response.status_code == 201
    community_id = community_response.json()["id"]

    login_response = client.post(
        "/login",
        data={"username": test_user2["email"], "password": test_user2["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Act: join the community.
    with (
        patch("app.routers.community.queue_email_notification") as mock_queue_email,
        patch(
            "app.routers.community.schedule_email_notification"
        ) as mock_schedule_email,
        patch(
            "app.routers.community.BackgroundTasks", return_value=mock_background_tasks
        ),
    ):
        join_response = client.post(
            f"/communities/{community_id}/join", headers=headers
        )

    # Assert: membership is created without sending emails.
    assert join_response.status_code == 200

    membership = (
        session.query(CommunityMember)
        .filter_by(community_id=community_id, user_id=test_user2["id"])
        .first()
    )
    assert membership is not None

    mock_queue_email.assert_not_called()
    mock_schedule_email.assert_not_called()


def _create_notification(
    session,
    user_id: int,
    content: str = "Test notification",
    priority: notification_models.NotificationPriority = notification_models.NotificationPriority.MEDIUM,
    is_read: bool = False,
    seen: bool = False,
):
    """Helper for  create notification."""
    notification = notification_models.Notification(
        user_id=user_id,
        content=content,
        notification_type="system_update",
        priority=priority,
        category=notification_models.NotificationCategory.SYSTEM,
        is_read=is_read,
        is_archived=False,
    )
    if is_read:
        notification.read_at = datetime.now(timezone.utc)
    if seen:
        notification.seen_at = datetime.now(timezone.utc)
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification


def test_notification_summary_endpoint(authorized_client, session, test_user):
    """Test case for test notification summary endpoint."""
    _create_notification(session, test_user["id"], content="welcome")
    _create_notification(
        session,
        test_user["id"],
        content="urgent",
        priority=notification_models.NotificationPriority.URGENT,
    )
    _create_notification(
        session,
        test_user["id"],
        content="old",
        is_read=True,
        seen=True,
    )

    response = authorized_client.get("/notifications/summary")
    assert response.status_code == 200
    payload = response.json()

    assert payload["unread_count"] == 2
    assert payload["unseen_count"] == 2
    assert payload["unread_urgent_count"] == 1
    assert payload["last_unread_at"] is not None
    assert payload["generated_at"] is not None


def test_notification_feed_marks_seen(authorized_client, session, test_user):
    """Test case for test notification feed marks seen."""
    _create_notification(session, test_user["id"], content="one")
    _create_notification(session, test_user["id"], content="two")
    _create_notification(session, test_user["id"], content="three")
    response = authorized_client.get("/notifications/feed", params={"limit": 2})
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["notifications"]) == 2
    assert payload["has_more"] is True
    assert payload["unseen_count"] == 1  # only the oldest notification remains unseen
    assert payload["unread_count"] == 3  # mark_seen does not mark as read by default
    assert payload["next_cursor"] is not None


# Add more notification tests as needed, for example:
# - Notifications for post updates
# - Notifications for comment replies
# - Notifications for community events
# - Notifications for admin actions
