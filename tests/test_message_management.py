import pytest
from app import models


@pytest.fixture
def test_message(authorized_client, test_user, session):
    message_data = {"recipient_id": test_user["id"], "content": "Test Message"}
    response = authorized_client.post("/messages/", json=message_data)
    assert response.status_code == 201
    message = response.json()
    session.add(models.Message(id=message["id"], **message_data))
    session.commit()
    return message


def test_send_message(authorized_client, test_user2):
    response = authorized_client.post(
        "/messages/", json={"recipient_id": test_user2["id"], "content": "Hello!"}
    )
    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "Hello!"
    assert message["receiver_id"] == test_user2["id"]


def test_get_messages(authorized_client, test_message):
    response = authorized_client.get("/messages/")
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) > 0
    assert messages[0]["content"] == "Test Message"


def test_send_file(authorized_client, test_user2):
    file_data = {
        "recipient_id": test_user2["id"],
        "file": ("testfile.txt", b"File content", "text/plain"),
    }
    response = authorized_client.post("/messages/send_file", files=file_data)
    assert response.status_code == 201
    assert response.json()["message"] == "File sent successfully"


def test_download_file(authorized_client, test_message):
    # نفترض أن هناك رسالة تحتوي على ملف تم إرساله مسبقًا
    file_name = "testfile.txt"
    response = authorized_client.get(f"/messages/download/{file_name}")
    assert response.status_code == 200
    assert "attachment" in response.headers.get("Content-Disposition", "")
