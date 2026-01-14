"""Targeted coverage tests for moderator routes."""

from sqlalchemy import func as sqlalchemy_func

from app import models
from app.core.app_factory import create_app
from app.modules.community import Community, CommunityMember, CommunityRole
from app.routers import moderator
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
    if not hasattr(db_session, "func"):
        db_session.func = sqlalchemy_func
    app = create_app()
    app.dependency_overrides[moderator.get_db] = lambda: db_session
    app.dependency_overrides[moderator.oauth2.get_current_user] = lambda: current_user
    return TestClient(app)


def _setup_community(session, owner):
    community = Community(name="CommMod", description="d", owner_id=owner.id)
    session.add(community)
    session.commit()
    session.refresh(community)
    return community


def test_moderator_reports_and_members(session):
    mod_user = _make_user(session, "mod@example.com", role=models.UserRole.MODERATOR)
    community = _setup_community(session, mod_user)
    member = CommunityMember(
        community_id=community.id,
        user_id=mod_user.id,
        role=CommunityRole.MODERATOR,
    )
    session.add(member)
    session.commit()

    post = models.Post(owner_id=mod_user.id, title="t", content="c", community_id=community.id)
    session.add(post)
    session.commit()
    session.refresh(post)
    report = models.Report(
        report_reason="spam",
        post_id=post.id,
        reporter_id=mod_user.id,
        reported_user_id=mod_user.id,
        status=models.ReportStatus.PENDING,
    )
    session.add(report)
    session.commit()

    client = _make_client(session, mod_user)
    reports = client.get(f"/moderator/community/{community.id}/reports?status_filter=pending")
    assert reports.status_code == 200
    reports_payload = reports.json()
    assert len(reports_payload) == 1
    assert reports_payload[0]["status"] == models.ReportStatus.PENDING.value

    members = client.get(f"/moderator/community/{community.id}/members")
    assert members.status_code == 200
    members_payload = members.json()
    assert len(members_payload) == 1
    assert members_payload[0]["user"]["id"] == mod_user.id


def test_moderator_reports_requires_moderator_flag(session):
    user = _make_user(session, "user2@example.com", role=models.UserRole.USER)
    user.is_moderator = False
    session.commit()
    client = _make_client(session, user)

    resp = client.get("/moderator/community/1/reports")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized"


def test_moderator_update_report_missing_post(session):
    mod_user = _make_user(session, "mod3@example.com", role=models.UserRole.MODERATOR)
    community = _setup_community(session, mod_user)
    member = CommunityMember(
        community_id=community.id,
        user_id=mod_user.id,
        role=CommunityRole.MODERATOR,
    )
    session.add(member)
    post = models.Post(owner_id=mod_user.id, title="t", content="c", community_id=community.id)
    session.add(post)
    session.commit()
    session.refresh(post)

    comment = models.Comment(owner_id=mod_user.id, post_id=post.id, content="c")
    session.add(comment)
    session.commit()
    session.refresh(comment)

    report = models.Report(
        report_reason="spam",
        comment_id=comment.id,
        reporter_id=mod_user.id,
        reported_user_id=mod_user.id,
        status=models.ReportStatus.PENDING,
    )
    session.add(report)
    session.commit()

    client = _make_client(session, mod_user)
    resp = client.put(
        f"/moderator/reports/{report.id}",
        json={"status": "reviewed", "resolution_notes": "note"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Associated post not found"


def test_moderator_update_report_and_roles(session):
    admin_user = _make_user(session, "admin@example.com", role=models.UserRole.MODERATOR)
    community = _setup_community(session, admin_user)
    admin_member = CommunityMember(
        community_id=community.id,
        user_id=admin_user.id,
        role=CommunityRole.ADMIN,
    )
    member_user = _make_user(session, "member@example.com", role=models.UserRole.USER)
    member = CommunityMember(
        community_id=community.id,
        user_id=member_user.id,
        role=CommunityRole.MEMBER,
    )
    session.add_all([admin_member, member])
    session.commit()

    post = models.Post(owner_id=member_user.id, title="t", content="c", community_id=community.id)
    session.add(post)
    session.commit()
    session.refresh(post)
    report = models.Report(
        report_reason="spam",
        post_id=post.id,
        reporter_id=admin_user.id,
        reported_user_id=member_user.id,
        status=models.ReportStatus.PENDING,
    )
    session.add(report)
    session.commit()

    client = _make_client(session, admin_user)
    updated = client.put(
        f"/moderator/reports/{report.id}",
        json={"status": "reviewed", "resolution_notes": "ok"},
    )
    assert updated.status_code == 200

    role_change = client.put(
        f"/moderator/community/{community.id}/member/{member_user.id}/role",
        json={"role": "moderator", "activity_score": 0},
    )
    assert role_change.status_code == 200

    missing = client.put(
        f"/moderator/community/{community.id}/member/99999/role",
        json={"role": "moderator", "activity_score": 0},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Member not found in this community"


def test_moderator_update_member_role_requires_admin(session):
    mod_user = _make_user(session, "mod4@example.com", role=models.UserRole.MODERATOR)
    community = _setup_community(session, mod_user)
    mod_member = CommunityMember(
        community_id=community.id,
        user_id=mod_user.id,
        role=CommunityRole.MODERATOR,
    )
    target = _make_user(session, "member2@example.com", role=models.UserRole.USER)
    member = CommunityMember(
        community_id=community.id,
        user_id=target.id,
        role=CommunityRole.MEMBER,
    )
    session.add_all([mod_member, member])
    session.commit()

    client = _make_client(session, mod_user)
    resp = client.put(
        f"/moderator/community/{community.id}/member/{target.id}/role",
        json={"role": "moderator", "activity_score": 0},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not authorized to change roles in this community"
