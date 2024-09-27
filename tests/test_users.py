# import pytest
# from jose import jwt
# from app import schemas
# from app.config import settings
# from app.models import User
# from app.oauth2 import create_access_token
# from datetime import datetime, timedelta


# def test_create_user(client):
#     res = client.post(
#         "/users/", json={"email": "test@example.com", "password": "password123"}
#     )
#     new_user = schemas.UserOut(**res.json())
#     assert new_user.email == "test@example.com"
#     assert res.status_code == 201


# def test_login_user(client, test_user):
#     res = client.post(
#         "/login",
#         data={"username": test_user["email"], "password": test_user["password"]},
#     )
#     login_res = schemas.Token(**res.json())
#     payload = jwt.decode(
#         login_res.access_token, settings.secret_key, algorithms=[settings.algorithm]
#     )
#     id = payload.get("user_id")
#     assert id == test_user["id"]
#     assert login_res.token_type == "bearer"
#     assert res.status_code == 200


# @pytest.mark.parametrize(
#     "email, password, status_code",
#     [
#         ("wrongemail@gmail.com", "password123", 403),
#         ("test@example.com", "wrongpassword", 403),
#         ("wrongemail@gmail.com", "wrongpassword", 403),
#         (None, "password123", 422),
#         ("test@example.com", None, 422),
#     ],
# )
# def test_incorrect_login(client, test_user, email, password, status_code):
#     res = client.post("/login", data={"username": email, "password": password})
#     assert res.status_code == status_code


# def test_get_user(authorized_client, test_user):
#     res = authorized_client.get(f"/users/{test_user['id']}")
#     user = schemas.UserOut(**res.json())
#     assert user.email == test_user["email"]
#     assert user.id == test_user["id"]
#     assert res.status_code == 200


# def test_get_non_exist_user(authorized_client):
#     res = authorized_client.get(f"/users/99999")
#     assert res.status_code == 404


# def test_verify_user(authorized_client, test_user, tmp_path):
#     # Create a temporary file for testing
#     d = tmp_path / "verification"
#     d.mkdir()
#     p = d / "test.pdf"
#     p.write_text("Test verification document")

#     with open(p, "rb") as f:
#         res = authorized_client.post(
#             "/users/verify", files={"file": ("test.pdf", f, "application/pdf")}
#         )

#     assert res.status_code == 200
#     assert (
#         res.json()["info"]
#         == "Verification document uploaded and user verified successfully."
#     )

#     # Check if the user is now verified in the database
#     # This might require querying the database directly, which depends on your test setup
#     # For example:
#     # updated_user = db.query(User).filter(User.id == test_user["id"]).first()
#     # assert updated_user.is_verified == True


# def test_verify_user_invalid_file(authorized_client):
#     res = authorized_client.post(
#         "/users/verify", files={"file": ("test.txt", b"Test content", "text/plain")}
#     )
#     assert res.status_code == 400
#     assert res.json()["detail"] == "Unsupported file type."


# # You might want to add more user-related tests here, such as:
# # - Test updating user information
# # - Test deleting a user account
# # - Test password reset functionality (if implemented)
# # - Test user search functionality (if implemented)
# # - Test any user preferences or settings
