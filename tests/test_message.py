import pytest
from app import models, schemas, oauth2
from app.database import get_db
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from fastapi import UploadFile
from io import BytesIO
from unittest.mock import patch, MagicMock
from app.routers import message as message_router


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


# @patch("os.path.exists")
# @patch("app.routers.message.FileResponse")
# def test_download_file(
#     mock_file_response, mock_path_exists, authorized_client, session
# ):
#     print("Starting test_download_file")

#     mock_path_exists.return_value = True
#     mock_file_response.return_value = FileResponse(path="dummy_path")

#     # Create a test message in the database
#     test_message = models.Message(
#         sender_id=1, receiver_id=2, content="static/messages/test.txt"
#     )
#     session.add(test_message)
#     session.commit()

#     file_name = "test.txt"

#     print(f"Attempting to download file: {file_name}")

#     response = authorized_client.get(f"/message/download/{file_name}")
#     print(f"Response status code: {response.status_code}")
#     print(f"Response content: {response.content}")

#     print("Checking assertions")

#     assert (
#         response.status_code == 200
#     ), f"Unexpected status code: {response.status_code}"

#     mock_path_exists.assert_called_once_with("static/messages/test.txt")
#     mock_file_response.assert_called_once_with(
#         path="static/messages/test.txt", filename="test.txt"
#     )

#     print("Test completed successfully")


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
def test_send_file(mock_scan, authorized_client, test_user2):
    mock_scan.return_value = True  # Симулируем чистый файл
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
    mock_scan.return_value = True  # Симулируем чистый файл
    large_file_content = b"0" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
    files = {"file": ("large.txt", large_file_content, "text/plain")}
    data = {"recipient_id": test_user2["id"]}
    response = authorized_client.post("/message/send_file", files=files, data=data)
    assert response.status_code == 413
    assert "File is too large" in response.json()["detail"]


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
    # Создаем блокировку
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
        (1, "x" * 1001, 422),  # Предполагаем, что максимальная длина контента 1000
    ],
)
def test_send_message_invalid_input(
    authorized_client, recipient_id, content, status_code
):
    message_data = {"recipient_id": recipient_id, "content": content}
    response = authorized_client.post("/message/", json=message_data)
    assert response.status_code == status_code


def test_get_messages_pagination(authorized_client, test_user, test_user2, session):
    # Создаем 25 сообщений
    for i in range(25):
        message = models.Message(
            sender_id=test_user["id"],
            receiver_id=test_user2["id"],
            content=f"Message {i}",
        )
        session.add(message)
    session.commit()

    # Тестируем первую страницу
    response = authorized_client.get("/message/?skip=0&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    # Тестируем вторую страницу
    response = authorized_client.get("/message/?skip=10&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 10

    # Тестируем последнюю страницу
    response = authorized_client.get("/message/?skip=20&limit=10")
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)
    assert len(messages) == 5


def test_get_messages_order(authorized_client, test_user, test_user2, session):
    # Создаем сообщения с разными временными метками
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
    # Проверяем, что сообщения в порядке убывания по временной метке
    assert (
        messages[0]["timestamp"] > messages[1]["timestamp"] > messages[2]["timestamp"]
    )
