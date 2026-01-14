"""Test module for test users."""
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwt

from app import schemas
from app.core.config import settings


def test_create_user(client):
    """Test case for test create user."""
    res = client.post(
        "/users/", json={"email": "test@example.com", "password": "password123"}
    )
    new_user = schemas.UserOut(**res.json())
    assert new_user.email == "test@example.com"
    assert res.status_code == 201


def test_login_user(client, test_user):
    """Test case for test login user."""
    res = client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    login_res = schemas.Token(**res.json())

    public_key = serialization.load_pem_public_key(
        settings.rsa_public_key.encode(), backend=default_backend()
    )
    payload = jwt.decode(
        login_res.access_token, public_key, algorithms=[settings.algorithm]
    )
    id = payload.get("user_id")
    assert id == test_user["id"]
    assert login_res.token_type == "bearer"
    assert res.status_code == 200


@pytest.mark.parametrize(
    "email, password, status_code",
    [
        ("wrongemail@gmail.com", "password123", 403),
        ("test@example.com", "wrongpassword", 403),
        ("wrongemail@gmail.com", "wrongpassword", 403),
        (None, "password123", 403),
        ("test@example.com", None, 403),
    ],
)
def test_incorrect_login(client, test_user, email, password, status_code):
    """Test case for test incorrect login."""
    res = client.post("/login", data={"username": email, "password": password})
    assert res.status_code == status_code
    assert res.json().get("detail") == "Invalid Credentials"


def test_get_user(authorized_client, test_user):
    """Test case for test get user."""
    res = authorized_client.get(f"/users/{test_user['id']}")
    user = schemas.UserOut(**res.json())
    assert user.email == test_user["email"]
    assert user.id == test_user["id"]
    assert res.status_code == 200


def test_get_non_exist_user(authorized_client):
    """Test case for test get non exist user."""
    res = authorized_client.get("/users/99999")
    assert res.status_code == 404
    assert res.json()["detail"] == "User not found"


def test_verify_user(authorized_client, test_user, tmp_path):
    """Test case for test verify user."""
    d = tmp_path / "verification"
    d.mkdir()
    p = d / "test.pdf"
    p.write_text("Test verification document")

    with open(p, "rb") as f:
        res = authorized_client.post(
            "/users/verify", files={"file": ("test.pdf", f, "application/pdf")}
        )

    assert res.status_code == 200
    assert (
        res.json()["info"]
        == "Verification document uploaded and user verified successfully."
    )


def test_verify_user_invalid_file(authorized_client):
    """Test case for test verify user invalid file."""
    res = authorized_client.post(
        "/users/verify", files={"file": ("test.txt", b"Test content", "text/plain")}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Unsupported file type."
