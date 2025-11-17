import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.oauth2 import create_access_token, verify_access_token
from app.notifications import send_email_notification
import logging

logger = logging.getLogger(__name__)


def test_authentication():
    user_id = 1
    token = create_access_token({"user_id": user_id})

    try:
        token_data = verify_access_token(
            token,
            credentials_exception=HTTPException(
                status_code=401, detail="Invalid credentials"
            ),
        )
        assert (
            token_data.id == user_id
        ), f"Expected user_id {user_id}, got {token_data.id}"
    except HTTPException as e:
        logger.error(f"Authentication failed with error: {e.detail}")
        assert False, "Token verification failed"


def test_unauthorized_access(client):
    res = client.get("/protected-resource")
    assert res.status_code == 401


def test_invalid_login(client):
    res = client.post(
        "/login", data={"username": "wrong@example.com", "password": "wrongpassword"}
    )
    assert res.status_code == 403
    assert res.json().get("detail") == "Invalid Credentials"


@pytest.mark.asyncio
async def test_valid_login(client, test_user):
    res = client.post(
        "/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    assert res.status_code == 200
    token = res.json().get("access_token")
    assert token is not None, "Expected a token in the response"

    try:
        token_data = verify_access_token(
            token, HTTPException(status_code=401, detail="Invalid token")
        )
        assert (
            token_data.id == test_user["id"]
        ), f"Expected user_id {test_user['id']} in the token payload"
    except HTTPException as e:
        pytest.fail(f"Token verification failed: {e.detail}")

    # Sending email notification
    await send_email_notification(
        to=test_user["email"],
        subject="Successful Login",
        body="You have successfully logged in to your account.",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email, password, status_code",
    [
        ("wrongemail@example.com", "password123", 403),
        ("testuser@example.com", "wrongpassword", 403),
        ("wrongemail@example.com", "wrongpassword", 403),
        (None, "password123", 403),
        ("testuser@example.com", None, 403),
    ],
)
async def test_invalid_login_param(client, test_user, email, password, status_code):
    res = client.post("/login", data={"username": email, "password": password})
    assert (
        res.status_code == status_code
    ), f"Expected status code {status_code}, got {res.status_code}"

    if status_code == 403:
        await send_email_notification(
            to=email if email else "unknown@example.com",
            subject="Failed Login Attempt",
            body="There was a failed login attempt on your account.",
        )


def test_token_creation_and_verification():
    user_id = 1
    token = create_access_token({"user_id": user_id})
    token_data = verify_access_token(token, HTTPException(status_code=401))
    assert token_data.id == user_id
