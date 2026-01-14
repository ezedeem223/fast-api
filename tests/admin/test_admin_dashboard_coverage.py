"""Targeted coverage tests for admin dashboard routes and helpers."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import analytics, models
from app.core.app_factory import create_app
from app.modules.community import Community, CommunityMember, CommunityRole
from app.modules.fact_checking.models import Fact, FactCheckStatus
from app.routers import admin_dashboard
from fastapi.responses import HTMLResponse
from tests.testclient import TestClient


def _make_admin(session, email="admin@example.com"):
    user = models.User(
        email=email,
        hashed_password="x",
        is_verified=True,
        role=models.UserRole.ADMIN,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_client(db_session, current_user):
    app = create_app()
    app.dependency_overrides[admin_dashboard.get_db] = lambda: db_session
    app.dependency_overrides[admin_dashboard.get_current_admin] = lambda: current_user
    app.dependency_overrides[admin_dashboard.oauth2.get_current_admin] = (
        lambda: current_user
    )
    return TestClient(app)


def test_hashable_and_async_cache():
    admin_dashboard.admin_cache.clear()
    assert admin_dashboard._hashable(123) == 123
    assert isinstance(admin_dashboard._hashable({"a": 1}), str)

    calls = {"count": 0}

    @admin_dashboard.async_cached(admin_dashboard.admin_cache)
    async def _cached(value):
        calls["count"] += 1
        return value

    first = asyncio.run(_cached({"a": 1}))
    second = asyncio.run(_cached({"a": 1}))
    assert first == second
    assert calls["count"] == 1


def test_admin_dashboard_template_response(monkeypatch, session):
    admin = _make_admin(session)
    client = _make_client(session, admin)

    monkeypatch.setattr(
        admin_dashboard,
        "templates",
        SimpleNamespace(TemplateResponse=lambda *args, **kwargs: HTMLResponse("ok")),
    )
    monkeypatch.setattr(admin_dashboard, "generate_search_trends_chart", lambda: "chart")
    monkeypatch.setattr(
        admin_dashboard, "get_popular_searches", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        admin_dashboard, "get_recent_searches", lambda *args, **kwargs: []
    )

    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_admin_stats_and_fact_checking(session):
    admin = _make_admin(session)
    client = _make_client(session, admin)
    admin_dashboard.admin_cache.clear()

    community = Community(name="Comm", description="d", owner_id=admin.id)
    session.add(community)
    session.add(models.Post(owner_id=admin.id, title="t", content="c"))
    session.add(
        models.Report(
            status=models.ReportStatus.PENDING,
            report_reason="spam",
            reporter_id=admin.id,
        )
    )
    session.commit()

    stats = client.get("/admin/stats")
    assert stats.status_code == 200
    assert stats.json()["total_users"] >= 1

    fact = Fact(
        claim="claim",
        submitter_id=admin.id,
        status=FactCheckStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    session.add(fact)
    session.commit()
    admin_dashboard.admin_cache.clear()

    fact_stats = client.get("/admin/fact-check/stats")
    assert fact_stats.status_code == 200
    assert "counts" in fact_stats.json()


def test_admin_users_sorting_and_role_update(session):
    admin = _make_admin(session)
    user1 = models.User(email="aaa@example.com", hashed_password="x", is_verified=True)
    user2 = models.User(email="bbb@example.com", hashed_password="x", is_verified=True)
    session.add_all([user1, user2])
    session.commit()

    client = _make_client(session, admin)
    resp = client.get("/admin/users?sort_by=email&order=asc")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == sorted(emails)

    missing_role = client.put(f"/admin/users/{user1.id}/role", json={})
    assert missing_role.status_code == 422

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin_dashboard.update_user_role(
                user1.id,
                SimpleNamespace(role=None),
                db=session,
                current_admin=admin,
            )
        )
    assert exc.value.status_code == 400

    update = client.put(f"/admin/users/{user1.id}/role", json={"role": "admin"})
    assert update.status_code == 200

    not_found = client.put("/admin/users/99999/role", json={"role": "admin"})
    assert not_found.status_code == 404


def test_admin_reports_and_communities_overview(session):
    admin = _make_admin(session)
    client = _make_client(session, admin)
    admin_dashboard.admin_cache.clear()

    community = Community(
        name="Comm2", description="d", owner_id=admin.id, is_active=True
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    member = CommunityMember(
        community_id=community.id,
        user_id=admin.id,
        role=CommunityRole.OWNER,
    )
    session.add(member)
    session.add(
        models.Report(
            status=models.ReportStatus.RESOLVED,
            report_reason="spam",
            reporter_id=admin.id,
            reported_user_id=admin.id,
        )
    )
    session.commit()

    reports = client.get("/admin/reports/overview")
    assert reports.status_code == 200
    assert reports.json()["resolved_reports"] >= 1

    comms = client.get("/admin/communities/overview")
    assert comms.status_code == 200
    assert comms.json()["active_communities"] >= 1


def test_admin_user_activity_and_problematic_users(session):
    admin = _make_admin(session)
    client = _make_client(session, admin)
    admin_dashboard.admin_cache.clear()

    target = models.User(
        email="target@example.com",
        hashed_password="x",
        is_verified=True,
    )
    session.add(target)
    session.commit()
    session.refresh(target)

    session.add(
        models.UserEvent(
            user_id=target.id,
            event_type="login",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        models.Report(
            report_reason="spam",
            reporter_id=admin.id,
            reported_user_id=target.id,
            is_valid=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    activity = client.get(f"/admin/user-activity/{target.id}?days=7")
    assert activity.status_code == 200
    assert activity.json().get("login") == 1

    problematic = client.get("/admin/problematic-users?threshold=1")
    assert problematic.status_code == 200
    assert any(user["id"] == target.id for user in problematic.json())


def test_admin_ban_stats_and_distributions(session, monkeypatch):
    admin = _make_admin(session)
    client = _make_client(session, admin)
    admin_dashboard.admin_cache.clear()

    session.add(models.UserBan(user_id=admin.id, reason="rule", duration=timedelta(days=1)))
    session.add(
        models.BanStatistics(
            date=date.today(),
            total_bans=2,
            ip_bans=1,
            word_bans=0,
            user_bans=1,
            effectiveness_score=0.5,
        )
    )
    session.add(models.BanReason(reason="spam", count=3))
    session.commit()

    stats_row = analytics.get_ban_statistics(session)
    assert stats_row.total_bans >= 1

    monkeypatch.setattr(
        admin_dashboard,
        "get_ban_statistics",
        lambda db: {"total_bans": stats_row.total_bans, "avg_duration": 0},
    )

    stats = client.get("/admin/ban-statistics")
    assert stats.status_code == 200

    overview = client.get("/admin/ban-overview")
    assert overview.status_code == 200
    assert overview.json()["total_bans"] >= 1

    reasons = client.get("/admin/common-ban-reasons?sort_by=reason&order=asc")
    assert reasons.status_code == 200
    assert reasons.json()[0]["reason"] == "spam"

    trend = client.get("/admin/ban-effectiveness-trend?days=30")
    assert trend.status_code == 200

    distribution = client.get("/admin/ban-type-distribution?days=30")
    assert distribution.status_code == 200


def test_admin_requires_admin(session):
    user = models.User(email="user@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()

    app = create_app()
    app.dependency_overrides[admin_dashboard.get_db] = lambda: session
    app.dependency_overrides[admin_dashboard.oauth2.get_current_user] = lambda: user
    client = TestClient(app)

    resp = client.get("/admin/users")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized"
