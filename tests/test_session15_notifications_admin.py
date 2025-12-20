from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import models
from app.core.database import get_db
from app.routers import notifications as notifications_router
from app.oauth2 import get_current_user


def _user(session, email="n@example.com", is_admin=False):
    u = models.User(email=email, hashed_password="x", is_verified=True, is_admin=is_admin)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _client_with_db(session, current_user):
    app = FastAPI()
    app.include_router(notifications_router.router)

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def test_notifications_list_pagination_and_include_read(session):
    user = _user(session, "list@example.com")
    other = _user(session, "other@example.com")
    notes = [
        models.Notification(user_id=user.id, content="u1", notification_type="t"),
        models.Notification(user_id=user.id, content="u2", notification_type="t"),
        models.Notification(user_id=user.id, content="read", notification_type="t", is_read=True),
        models.Notification(user_id=other.id, content="other", notification_type="t"),
    ]
    session.add_all(notes)
    session.commit()

    client = _client_with_db(session, user)
    resp = client.get("/notifications", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # pagination enforced

    resp_all = client.get("/notifications", params={"limit": 10, "include_read": True})
    assert len(resp_all.json()) == 3  # include read adds third


def test_mark_notification_wrong_user_and_not_found(session):
    user = _user(session, "mark@example.com")
    other = _user(session, "mark2@example.com")
    note = models.Notification(user_id=other.id, content="other", notification_type="t")
    session.add(note)
    session.commit()

    client = _client_with_db(session, user)
    resp = client.put(f"/notifications/{note.id}/read")
    assert resp.status_code == 404  # wrong user should not find it

    resp_missing = client.put("/notifications/999999/read")
    assert resp_missing.status_code == 404
