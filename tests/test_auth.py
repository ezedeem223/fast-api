import pytest
from jose import jwt
from fastapi import HTTPException
from app import schemas
from app.config import settings
from app.oauth2 import create_access_token, verify_access_token
import logging

logger = logging.getLogger(__name__)


def test_authentication():
    user_id = 1
    token = create_access_token({"user_id": user_id})

    try:
        token_data = verify_access_token(token)
        assert (
            token_data["user_id"] == user_id
        ), f"Expected user_id {user_id}, got {token_data['user_id']}"
    except HTTPException as e:
        logger.error(f"Authentication failed with error: {e.detail}")
        assert False, "Token verification failed"


# def test_unauthorized_access(client):
#     res = client.get("/protected-resource")
#     assert res.status_code == 401  # Unauthorized


# def test_invalid_login(client):
#     res = client.post(
#         "/login", data={"username": "wrong@example.com", "password": "wrongpassword"}
#     )
#     assert res.status_code == 403  # Forbidden
#     assert res.json().get("detail") == "Invalid Credentials"


# def test_valid_login(client, test_user):
#     res = client.post(
#         "/login",
#         data={"username": test_user["email"], "password": test_user["password"]},
#     )
#     assert res.status_code == 200  # OK
#     token = res.json().get("access_token")
#     assert token is not None

#     # Verify the token
#     payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
#     assert payload.get("user_id") == test_user["id"]


# @pytest.mark.parametrize(
#     "email, password, status_code",
#     [
#         ("wrongemail@example.com", "password123", 403),
#         ("testuser@example.com", "wrongpassword", 403),
#         ("wrongemail@example.com", "wrongpassword", 403),
#         (None, "password123", 422),
#         ("testuser@example.com", None, 422),
#     ],
# )
# def test_invalid_login_param(client, test_user, email, password, status_code):
#     res = client.post("/login", data={"username": email, "password": password})
#     assert res.status_code == status_code
