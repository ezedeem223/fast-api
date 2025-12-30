from unittest.mock import patch

import pytest

from app import models
from app.modules.messaging.models import Conversation


def _ensure_conversation(session, user_a_id: int, user_b_id: int) -> str:
    """Create a conversation row for the two users if missing."""
    user_a, user_b = sorted((user_a_id, user_b_id))
    conv_id = f"{user_a}-{user_b}"
    existing = session.query(Conversation).filter_by(id=conv_id).first()
    if not existing:
        session.add(Conversation(id=conv_id, created_by=user_a))
        session.commit()
    return conv_id


@pytest.fixture
def test_message(authorized_client, test_user, test_user2, session):
    message_data = {"recipient_id": test_user2["id"], "content": "Test Message"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 201
    return response.json()


def test_get_inbox(authorized_client, test_message, test_user, test_user2):
    message_data = {"recipient_id": test_user["id"], "content": "Inbox Test Message"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 201

    response = authorized_client.get("/message/inbox")
    assert response.status_code == 200
    inbox = response.json()

    assert isinstance(inbox, list)
    assert len(inbox) > 0, "Inbox is empty"
    assert "message" in inbox[0]
    assert "count" in inbox[0]
    assert any(item["message"]["content"] == "Inbox Test Message" for item in inbox)


def test_get_messages(authorized_client, test_message):
    response = authorized_client.get("/message/")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) > 0
    assert "content" in messages[0]
    assert any(message["content"] == test_message["content"] for message in messages)


def test_send_message(authorized_client, test_user2):
    message_data = {"recipient_id": test_user2["id"], "content": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "Hello!"
    assert message["receiver_id"] == test_user2["id"]


def test_send_message_to_nonexistent_user(authorized_client):
    message_data = {"recipient_id": 99999, "content": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 422
    assert "User not found" in response.json()["detail"]


def test_send_empty_message(authorized_client, test_user2):
    message_data = {"recipient_id": test_user2["id"], "content": ""}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 422
    assert "Message content cannot be empty" in response.json()["detail"]


@patch("app.routers.message.scan_file_for_viruses")
def test_send_infected_file(mock_scan, authorized_client, test_user2):
    mock_scan.return_value = False
    file_content = b"infected"
    files = {"file": ("bad.txt", file_content, "text/plain")}
    data = {"recipient_id": test_user2["id"]}
    response = authorized_client.post("/message/send_file", files=files, data=data)
    assert response.status_code == 400
    assert "virus" in response.json()["detail"]


def test_download_nonexistent_file(authorized_client):
    file_name = "nonexistent.txt"
    response = authorized_client.get(f"/message/download/{file_name}")
    assert response.status_code == 404
    assert "File not found" in response.json()["detail"]


def test_send_message_to_blocked_user(
    authorized_client, test_user, test_user2, session
):
    block = models.Block(blocker_id=test_user2["id"], blocked_id=test_user["id"])
    session.add(block)
    session.commit()

    message_data = {"recipient_id": test_user2["id"], "content": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 422
    assert "You can't send messages to this user" in response.json()["detail"]


@pytest.mark.parametrize(
    "recipient_id, content, status_code",
    [
        (None, "Hello", 422),
        (1, None, 422),
        ("not_an_id", "Hello", 422),
        (1, "x" * 1001, 422),
    ],
)
def test_send_message_invalid_input(
    authorized_client, recipient_id, content, status_code
):
    message_data = {"recipient_id": recipient_id, "content": content}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == status_code


def test_get_messages_pagination(authorized_client, test_user, test_user2, session):
    _ensure_conversation(session, test_user["id"], test_user2["id"])
    for i in range(25):
        message = models.Message(
            sender_id=test_user["id"],
            receiver_id=test_user2["id"],
            content=f"Message {i}",
        )
        session.add(message)
    session.commit()

    response = authorized_client.get("/message/?skip=0&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    response = authorized_client.get("/message/?skip=10&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    response = authorized_client.get("/message/?skip=20&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 5


def test_get_messages_order(authorized_client, test_user, test_user2, session):
    _ensure_conversation(session, test_user["id"], test_user2["id"])
    for i in range(3):
        message = models.Message(
            sender_id=test_user["id"],
            receiver_id=test_user2["id"],
            content=f"Message {i}",
        )
        session.add(message)
        session.commit()
        session.refresh(message)

    response = authorized_client.get("/message/")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 3
    assert (
        messages[0]["timestamp"] > messages[1]["timestamp"] > messages[2]["timestamp"]
    )
