import pytest
from io import BytesIO
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_virus_scan():
    with patch("app.routers.message.scan_file_for_viruses", return_value=True):
        yield


@pytest.fixture
def test_file():
    file_content = b"This is a test file."
    return {"filename": "test_file.txt", "content": file_content}


def test_send_file(authorized_client, test_user, test_file):
    files = {"file": (test_file["filename"], test_file["content"])}
    response = authorized_client.post(
        "/message/send_file", files=files, data={"recipient_id": test_user["id"]}
    )
    assert response.status_code == 201
    assert response.json()["message"] == "File sent successfully"


def test_download_file(authorized_client, test_user, test_file):
    # First, send the file to create it on the server
    files = {"file": (test_file["filename"], test_file["content"])}
    send_response = authorized_client.post(
        "/message/send_file", files=files, data={"recipient_id": test_user["id"]}
    )
    assert send_response.status_code == 201

    # Then, attempt to download the file
    download_response = authorized_client.get(
        f"/message/download/{test_file['filename']}"
    )
    assert download_response.status_code == 200
    assert download_response.content == test_file["content"]


def test_send_file_with_invalid_user(authorized_client, test_file):
    files = {"file": (test_file["filename"], test_file["content"])}
    response = authorized_client.post(
        "/message/send_file", files=files, data={"recipient_id": 99999}
    )
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_send_empty_file(authorized_client, test_user):
    empty_file = {"filename": "empty_file.txt", "content": b""}
    files = {"file": (empty_file["filename"], BytesIO(empty_file["content"]))}
    response = authorized_client.post(
        "/message/send_file", files=files, data={"recipient_id": test_user["id"]}
    )
    assert (
        response.status_code == 400
    ), f"Expected 400, but got {response.status_code}. Response: {response.json()}"
    assert "File is empty" in response.json()["detail"]


def test_send_large_file(authorized_client, test_user):
    large_content = b"a" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
    large_file = {"filename": "large_file.txt", "content": large_content}
    files = {"file": (large_file["filename"], large_file["content"])}
    response = authorized_client.post(
        "/message/send_file", files=files, data={"recipient_id": test_user["id"]}
    )
    assert response.status_code == 413  # Payload Too Large
    assert "File is too large" in response.json()["detail"]


def test_protected_resource_access(authorized_client, test_user):
    response = authorized_client.get("/protected-resource")
    assert response.status_code == 200
    assert response.json()["message"] == "You have access to this protected resource"
    assert response.json()["user_id"] == test_user["id"]


def test_protected_resource_without_token(client):
    response = client.get("/protected-resource")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
