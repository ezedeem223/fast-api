"""Targeted coverage tests for moderation routes."""

from datetime import datetime, timezone

from app import models
from app.core.app_factory import create_app
from app.routers import moderation
from tests.testclient import TestClient


def _make_user(session, email: str, role=models.UserRole.USER):
    user = models.User(
        email=email,
        hashed_password="x",
        is_verified=True,
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_client(db_session, current_user):
    app = create_app()
    app.dependency_overrides[moderation.get_db] = lambda: db_session
    app.dependency_overrides[moderation.oauth2.get_current_user] = lambda: current_user
    return TestClient(app)


def test_moderation_warn_ban_and_unban(session):
    admin = _make_user(session, "admin@example.com", role=models.UserRole.ADMIN)
    target = _make_user(session, "target@example.com")
    client = _make_client(session, admin)

    warn = client.post(
        f"/moderation/warn/{target.id}",
        json={"reason": "be careful"},
    )
    assert warn.status_code == 200

    ban = client.post(
        f"/moderation/ban/{target.id}",
        json={"reason": "violation"},
    )
    assert ban.status_code == 200
    session.refresh(target)
    assert target.current_ban_end is not None

    unban = client.post(f"/moderation/unban/{target.id}")
    assert unban.status_code == 200
    session.refresh(target)
    assert target.current_ban_end is None


def test_moderation_requires_privileges(session):
    user = _make_user(session, "user@example.com", role=models.UserRole.USER)
    target = _make_user(session, "target2@example.com")
    client = _make_client(session, user)

    resp = client.post(f"/moderation/warn/{target.id}", json={"reason": "x"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized"

    resp = client.post(f"/moderation/ban/{target.id}", json={"reason": "x"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized"

    resp = client.post(f"/moderation/unban/{target.id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized"


def test_moderation_report_review_list_and_decision(session):
    moderator = _make_user(session, "mod@example.com", role=models.UserRole.MODERATOR)
    reporter = _make_user(session, "reporter@example.com")
    reported = _make_user(session, "reported@example.com")
    post = models.Post(owner_id=reported.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    report = models.Report(
        report_reason="spam",
        post_id=post.id,
        reporter_id=reporter.id,
        reported_user_id=reported.id,
        created_at=datetime.now(timezone.utc),
        status=models.ReportStatus.PENDING,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    client = _make_client(session, moderator)

    review = client.put(
        f"/moderation/reports/{report.id}/review",
        json={"is_valid": True},
    )
    assert review.status_code == 200

    listed = client.get("/moderation/reports?status_filter=pending")
    assert listed.status_code == 200

    decision = client.put(
        f"/moderation/reports/{report.id}/decision",
        json={"action": "delete", "resolution_notes": "removed"},
    )
    assert decision.status_code == 200
    session.refresh(post)
    assert post.is_deleted is True


def test_moderation_ip_ban_flow(session):
    admin = _make_user(session, "admin2@example.com", role=models.UserRole.ADMIN)
    user = _make_user(session, "user2@example.com", role=models.UserRole.USER)

    admin_client = _make_client(session, admin)
    user_client = _make_client(session, user)

    unauthorized = user_client.get("/moderation/ip")
    assert unauthorized.status_code == 403

    created = admin_client.post(
        "/moderation/ip",
        json={"ip_address": "192.168.1.1", "reason": "spam"},
    )
    assert created.status_code == 201

    duplicate = admin_client.post(
        "/moderation/ip",
        json={"ip_address": "192.168.1.1", "reason": "spam"},
    )
    assert duplicate.status_code == 400

    listed = admin_client.get("/moderation/ip")
    assert listed.status_code == 200
    assert listed.json()

    deleted = admin_client.delete("/moderation/ip/192.168.1.1")
    assert deleted.status_code == 204

    missing = admin_client.delete("/moderation/ip/192.168.1.1")
    assert missing.status_code == 404
