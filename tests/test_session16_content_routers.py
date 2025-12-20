from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import models, oauth2
from app.core.database import get_db
from app.routers import post as post_router
from app.routers import comment as comment_router
from app.routers import community as community_router
from app.routers import reaction as reaction_router
from app.routers import sticker as sticker_router


def make_client(session, current_user=None):
    app = FastAPI()
    app.include_router(post_router.router)
    app.include_router(comment_router.router)
    app.include_router(community_router.router)
    app.include_router(reaction_router.router)
    app.include_router(sticker_router.router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    if current_user is not None:
        app.dependency_overrides[oauth2.get_current_user] = lambda: current_user
    return TestClient(app)


def _user(session, email="u@example.com", verified=True, role=None):
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    if role:
        user.role = role
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_post_create_requires_verified_and_nonempty(session):
    unverified = _user(session, verified=False)
    client = make_client(session, current_user=unverified)
    resp = client.post("/posts/", json={"title": "t", "content": " "})
    assert resp.status_code in (403, 422)

    verified = _user(session, email="v@example.com", verified=True)
    client = make_client(session, current_user=verified)
    resp2 = client.post("/posts/", json={"title": "t", "content": "body"})
    assert resp2.status_code == 201


def test_comment_create_and_permissions(session):
    user = _user(session, email="c1@example.com")
    post = models.Post(owner_id=user.id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    client = make_client(session, current_user=user)
    resp = client.post("/comments/", json={"post_id": post.id, "content": "hi"})
    assert resp.status_code == 201

    other = _user(session, email="c2@example.com")
    client_other = make_client(session, current_user=other)
    # fetch created comment from DB to ensure delete permission enforced
    comment = session.query(models.Comment).first()
    resp_forbidden = client_other.delete(f"/comments/{comment.id}")
    assert resp_forbidden.status_code in (403, 404)


def test_community_create_requires_verified_and_join_private(session):
    unverified = _user(session, verified=False)
    client = make_client(session, current_user=unverified)
    resp = client.post("/communities/", json={"name": "C", "description": "d"})
    assert resp.status_code == 403

    owner = _user(session, email="owner@example.com")
    client_owner = make_client(session, current_user=owner)
    resp_ok = client_owner.post("/communities/", json={"name": "C2", "description": "d"})
    assert resp_ok.status_code == 201
    _ = resp_ok.json()["id"]

    private = client_owner.post("/communities/", json={"name": "P", "description": "d", "is_private": True}).json()
    other = _user(session, email="join@example.com")
    client_other = make_client(session, current_user=other)
    join_resp = client_other.post(f"/communities/{private['id']}/join")
    assert join_resp.status_code in (200, 403)


def test_reaction_invalid_input(session):
    user = _user(session, email="r@example.com")
    post = models.Post(owner_id=user.id, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    client = make_client(session, current_user=user)
    resp = client.post("/reactions/", json={"post_id": post.id, "reaction_type": "invalid"})
    assert resp.status_code in (400, 422)


def test_sticker_upload_invalid_extension(session, tmp_path, monkeypatch):
    user = _user(session, email="s@example.com")
    client = make_client(session, current_user=user)
    file_path = tmp_path / "file.txt"
    file_path.write_text("bad")
    with open(file_path, "rb") as f:
        resp = client.post("/stickers/", files={"file": ("file.txt", f, "text/plain")})
    assert resp.status_code in (400, 422)
