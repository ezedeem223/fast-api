import pytest
from fastapi import HTTPException

from app import models
from app.core.app_factory import create_app
from app.routers import admin_dashboard
from tests.conftest import TestingSessionLocal
from tests.testclient import TestClient


def make_client(db_session, current_user):
    app = create_app()
    app.dependency_overrides[admin_dashboard.get_db] = lambda: db_session
    app.dependency_overrides[admin_dashboard.get_current_admin] = lambda: current_user
    app.dependency_overrides[admin_dashboard.oauth2.get_current_admin] = lambda: current_user
    return TestClient(app)


def seed_admin(db):
    user = models.User(
        email="admin@example.com",
        hashed_password="x",
        is_verified=True,
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_admin_stats_overview_routes():
    with TestingSessionLocal() as db:
        admin = seed_admin(db)
        community = models.Community(name="Comm", description="d", owner_id=admin.id)
        community.members.append(models.CommunityMember(user_id=admin.id, role=models.CommunityRole.OWNER))
        db.add(community)
        db.add(models.Post(owner_id=admin.id, title="t", content="c"))
        db.add(
            models.Report(
                status="pending",
                report_reason="spam",
                reporter_id=admin.id,
                reported_user_id=admin.id,
            )
        )
        db.commit()

        client = make_client(db, admin)

        reports = client.get("/admin/reports/overview")
        assert reports.status_code == 200
        assert "total_reports" in reports.json()

        comms = client.get("/admin/communities/overview")
        assert comms.status_code == 200
        assert comms.json()["total_communities"] >= 1


def test_get_users_sort_and_role_update(monkeypatch):
    with TestingSessionLocal() as db:
        admin = seed_admin(db)
        user1 = models.User(email="a@example.com", hashed_password="x", is_verified=True)
        user2 = models.User(email="b@example.com", hashed_password="x", is_verified=True)
        db.add_all([user1, user2])
        db.commit()

        client = make_client(db, admin)
        resp = client.get("/admin/users?sort_by=email&order=asc")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert emails[0] <= emails[-1]

        update = client.put(f"/admin/users/{user1.id}/role", json={"role": "admin"})
        assert update.status_code == 200
        db.refresh(user1)
        assert user1.is_admin is True


def test_ban_statistics_and_common_reasons():
    with TestingSessionLocal() as db:
        admin = seed_admin(db)
        db.add(models.BanReason(reason="spam", count=5))
        from datetime import date

        db.add(
            models.BanStatistics(
                date=date.today(),
                total_bans=1,
                ip_bans=0,
                word_bans=1,
                user_bans=0,
                effectiveness_score=0.5,
            )
        )
        db.commit()

        client = make_client(db, admin)

        reasons = client.get("/admin/common-ban-reasons?sort_by=reason&order=asc")
        assert reasons.status_code == 200
        assert reasons.json()[0]["reason"] == "spam"


def test_admin_users_requires_admin_and_auth(monkeypatch):
    with TestingSessionLocal() as db:
        non_admin = models.User(
            email="u@example.com", hashed_password="x", is_verified=True, is_admin=False
        )
        db.add(non_admin)
        db.commit()

        app = create_app()
        app.dependency_overrides[admin_dashboard.get_db] = lambda: db
        # Use real get_current_admin but supply non-admin via oauth2 dependency
        app.dependency_overrides[admin_dashboard.oauth2.get_current_user] = (
            lambda: non_admin
        )
        client = TestClient(app)
        resp = client.get("/admin/users")
        assert resp.status_code == 403

        # Unauthenticated path returns 401
        def raise_unauth():
            raise HTTPException(status_code=401, detail="Unauthorized")

        app.dependency_overrides[
            admin_dashboard.oauth2.get_current_user
        ] = raise_unauth
        resp2 = client.get("/admin/users")
        assert resp2.status_code == 401
