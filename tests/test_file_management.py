# import pytest
# from fastapi import UploadFile
# from io import BytesIO
# from app import models


# @pytest.fixture
# def test_file():
#     file_content = b"This is a test file."
#     file = UploadFile(filename="test_file.txt", file=BytesIO(file_content))
#     return file


# def test_send_file(authorized_client, test_user, test_file):
#     response = authorized_client.post(
#         "/messages/send_file",
#         files={"file": test_file},
#         data={"recipient_id": test_user["id"]},
#     )
#     assert response.status_code == 201
#     assert response.json()["message"] == "File sent successfully"


# def test_download_file(authorized_client, test_file):
#     # First, send the file to create it on the server
#     response = authorized_client.post(
#         "/messages/send_file", files={"file": test_file}, data={"recipient_id": 1}
#     )
#     assert response.status_code == 201

#     # Then, attempt to download the file
#     file_name = test_file.filename
#     download_response = authorized_client.get(f"/messages/download/{file_name}")
#     assert download_response.status_code == 200
#     assert download_response.content == b"This is a test file."


# def test_send_file_with_invalid_user(authorized_client, test_file):
#     response = authorized_client.post(
#         "/messages/send_file", files={"file": test_file}, data={"recipient_id": 99999}
#     )
#     assert response.status_code == 404
#     assert response.json()["detail"] == "User not found"


# def test_send_empty_file(authorized_client, test_user):
#     empty_file = UploadFile(filename="empty_file.txt", file=BytesIO(b""))
#     response = authorized_client.post(
#         "/messages/send_file",
#         files={"file": empty_file},
#         data={"recipient_id": test_user["id"]},
#     )
#     assert response.status_code == 400
#     assert response.json()["detail"] == "File is empty"


# def test_send_large_file(authorized_client, test_user):
#     large_content = b"a" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
#     large_file = UploadFile(filename="large_file.txt", file=BytesIO(large_content))
#     response = authorized_client.post(
#         "/messages/send_file",
#         files={"file": large_file},
#         data={"recipient_id": test_user["id"]},
#     )
#     assert response.status_code == 413  # Payload Too Large
#     assert response.json()["detail"] == "File is too large"
