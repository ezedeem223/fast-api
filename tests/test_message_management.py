import pytest
from app import models, schemas
from app.database import get_db
from sqlalchemy.orm import Session
from fastapi import UploadFile
from io import BytesIO
from unittest.mock import patch


@pytest.fixture
def test_message(authorized_client, test_user, test_user2, session):
    message_data = {"recipient_id": test_user2["id"], "content": "Test Message"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 201
    message = response.json()
    new_message = models.Message(**message)
    session.add(new_message)
    session.commit()
    return new_message


def test_send_message(authorized_client, test_user2):
    message_data = {"recipient_id": test_user2["id"], "content": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "Hello!"
    assert message["receiver_id"] == test_user2["id"]


def test_send_message_to_nonexistent_user(authorized_client):
    message_data = {"recipient_id": 99999, "message": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_send_empty_message(authorized_client, test_user2):
    message_data = {"recipient_id": test_user2["id"], "message": ""}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 422  # Assuming empty content is not allowed


def test_get_messages(authorized_client, test_message):
    response = authorized_client.get("/message/")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) > 0
    assert "content" in messages[0]
    assert messages[0]["content"] == "Test Message"


def test_get_inbox(authorized_client, test_message):
    response = authorized_client.get("/message/inbox")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) > 0
    assert "message" in messages[0]
    assert messages[0]["message"]["content"] == "Test Message"
    assert "count" in messages[0]


@patch("app.routers.message.scan_file_for_viruses")
def test_send_file(mock_scan, authorized_client, test_user2):
    mock_scan.return_value = True  # Simulate a clean file
    file_content = b"This is a test file content"
    files = {"file": ("test.txt", file_content, "text/plain")}
    data = {"recipient_id": test_user2["id"]}
    response = authorized_client.post("/message/send_file", files=files, data=data)
    assert response.status_code == 201
    assert response.json()["message"] == "File sent successfully"


def test_send_empty_file(authorized_client, test_user2):
    files = {"file": ("empty.txt", b"", "text/plain")}
    data = {"recipient_id": test_user2["id"]}
    response = authorized_client.post("/message/send_file", files=files, data=data)
    assert response.status_code == 400
    assert "File is empty" in response.json()["detail"]


@patch("app.routers.message.scan_file_for_viruses")
def test_send_large_file(mock_scan, authorized_client, test_user2):
    mock_scan.return_value = True  # Simulate a clean file
    large_file_content = b"0" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
    files = {"file": ("large.txt", large_file_content, "text/plain")}
    data = {"recipient_id": test_user2["id"]}
    response = authorized_client.post("/message/send_file", files=files, data=data)
    assert response.status_code == 413
    assert "File is too large" in response.json()["detail"]


def test_download_file(authorized_client, test_message, monkeypatch):
    # Mock the file existence check
    def mock_path_exists(path):
        return True

    monkeypatch.setattr("os.path.exists", mock_path_exists)

    # Mock the FileResponse
    class MockFileResponse:
        def __init__(self, path, filename):
            self.path = path
            self.filename = filename

    monkeypatch.setattr("fastapi.responses.FileResponse", MockFileResponse)

    file_name = "test.txt"
    response = authorized_client.get(f"/message/download/{file_name}")
    assert response.status_code == 200
    assert isinstance(response, MockFileResponse)
    assert response.filename == file_name


def test_download_nonexistent_file(authorized_client):
    file_name = "nonexistent.txt"
    response = authorized_client.get(f"/message/download/{file_name}")
    assert response.status_code == 404
    assert "File not found" in response.json()["detail"]


def test_unauthorized_access(client):
    response = client.get("/message/")
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


def test_send_message_to_blocked_user(
    authorized_client, test_user, test_user2, session
):
    # Create a block
    block = models.Block(blocker_id=test_user2["id"], blocked_id=test_user["id"])
    session.add(block)
    session.commit()

    message_data = {"recipient_id": test_user2["id"], "message": "Hello!"}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == 403
    assert "You can't send messages to this user" in response.json()["detail"]


@pytest.mark.parametrize(
    "recipient_id, message, status_code",
    [
        (None, "Hello", 422),
        (1, None, 422),
        ("not_an_id", "Hello", 422),
        (1, "x" * 1001, 422),  # Assuming max content length is 1000
    ],
)
def test_send_message_invalid_input(
    authorized_client, recipient_id, message, status_code
):
    message_data = {"recipient_id": recipient_id, "message": message}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == status_code


def test_get_messages_pagination(authorized_client, test_user, test_user2, session):
    # Create 25 messages
    for i in range(25):
        message = models.Message(
            sender_id=test_user["id"],
            receiver_id=test_user2["id"],
            content=f"Message {i}",
        )
        session.add(message)
    session.commit()

    # Test first page
    response = authorized_client.get("/message/?skip=0&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    # Test second page
    response = authorized_client.get("/message/?skip=10&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    # Test last page
    response = authorized_client.get("/message/?skip=20&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 5


def test_get_messages_order(authorized_client, test_user, test_user2, session):
    # Create messages with different timestamps
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
    # Check if messages are in descending order of timestamp
    assert (
        messages[0]["timestamp"] > messages[1]["timestamp"] > messages[2]["timestamp"]
    )
