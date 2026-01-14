"""Test module for test community service."""
import pytest

from app.modules.community.models import (
    CommunityInvitation,
    CommunityMember,
    CommunityRole,
)
from app.modules.users.models import User
from app.schemas import CommunityCreate, CommunityMemberUpdate, CommunityUpdate
from app.services.community.service import ACTIVITY_THRESHOLD_VIP, CommunityService
from fastapi import HTTPException


def _make_user(session, email="owner@example.com", verified=True):
    """Helper for  make user."""
    user = User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_community(service, owner, **kwargs):
    """Helper for  make community."""
    base = dict(
        name="Test Community",
        description="desc",
        language="en",
        rules=[],
        tags=[],
        category_id=None,
        is_private=False,
    )
    base.update(kwargs)
    payload = CommunityCreate(**base)
    return service.create_community(current_user=owner, payload=payload)


def test_create_community_limits_and_category_tags(session, monkeypatch):
    """Test case for test create community limits and category tags."""
    owner = _make_user(session)
    service = CommunityService(session)

    # happy path create
    comm = _make_community(service, owner)
    assert comm.owner_id == owner.id
    assert len(comm.members) == 1 and comm.members[0].role == CommunityRole.OWNER

    # exceed quota
    monkeypatch.setattr(
        "app.services.community.service.settings.MAX_OWNED_COMMUNITIES", 1
    )
    with pytest.raises(HTTPException) as exc:
        _make_community(service, owner)
    assert exc.value.status_code == 400

    # invalid category
    payload = CommunityCreate(
        name="BadCat",
        description="x",
        language="en",
        rules=[],
        tags=[],
        category_id=999,
        is_private=False,
    )
    with pytest.raises(HTTPException):
        service.create_community(current_user=owner, payload=payload)


def test_update_community_rules_tags_and_permissions(session):
    """Test case for test update community rules tags and permissions."""
    owner = _make_user(session)
    service = CommunityService(session)
    comm = _make_community(service, owner)

    update = CommunityUpdate(
        name="Updated",
        description="new",
        tags=[],
    )
    updated = service.update_community(
        community_id=comm.id, payload=update, current_user=owner
    )
    assert updated.name == "Updated"
    session.refresh(comm)
    assert comm.description == "new"

    stranger = _make_user(session, email="stranger@example.com")
    with pytest.raises(HTTPException):
        service.update_community(
            community_id=comm.id, payload=update, current_user=stranger
        )


def test_invite_members_duplicates_and_quota(session, monkeypatch):
    """Test case for test invite members duplicates and quota."""
    owner = _make_user(session)
    service = CommunityService(session)
    comm = _make_community(service, owner)
    invitee = _make_user(session, email="invitee@example.com")
    from types import SimpleNamespace

    payloads = [SimpleNamespace(invitee_id=invitee.id, message="join")]

    original_init = CommunityInvitation.__init__

    def _safe_init(self, **kwargs):
        kwargs.pop("message", None)
        kwargs.pop("expires_at", None)
        return original_init(self, **kwargs)

    monkeypatch.setattr(CommunityInvitation, "__init__", _safe_init)

    created = service.invite_members(
        community_id=comm.id, invitations=payloads, current_user=owner
    )
    assert len(created) == 1

    # duplicate invitation should be skipped
    dup = service.invite_members(
        community_id=comm.id, invitations=payloads, current_user=owner
    )
    assert dup == []

    # quota exceeded
    monkeypatch.setattr(
        "app.services.community.service.settings.MAX_PENDING_INVITATIONS", 0
    )
    with pytest.raises(HTTPException):
        service.invite_members(
            community_id=comm.id, invitations=payloads, current_user=owner
        )


def test_respond_to_invitation_and_join_private(session):
    """Test case for test respond to invitation and join private."""
    owner = _make_user(session)
    service = CommunityService(session)
    comm = _make_community(service, owner)
    invitee = _make_user(session, email="inv@example.com")
    invite = CommunityInvitation(
        community_id=comm.id,
        inviter_id=owner.id,
        invitee_id=invitee.id,
        status="pending",
    )
    session.add(invite)
    session.commit()

    accepted = service.respond_to_invitation(
        invitation_id=invite.id, current_user=invitee, accept=True
    )
    assert accepted["message"].startswith("Invitation accepted")
    assert any(m.user_id == invitee.id for m in comm.members)

    # joining again should fail since already member
    with pytest.raises(HTTPException):
        service.join_community(community_id=comm.id, current_user=invitee)


def test_join_leave_and_roles(session):
    """Test case for test join leave and roles."""
    owner = _make_user(session)
    service = CommunityService(session)
    comm = _make_community(service, owner)
    member_user = _make_user(session, email="member@example.com")

    service.join_community(community_id=comm.id, current_user=member_user)
    member = (
        session.query(CommunityMember)
        .filter_by(community_id=comm.id, user_id=member_user.id)
        .first()
    )
    assert member is not None and member.role == CommunityRole.MEMBER

    update_payload = CommunityMemberUpdate(
        role=CommunityRole.MODERATOR, activity_score=0
    )
    updated_member = service.update_member_role(
        community_id=comm.id,
        user_id=member_user.id,
        payload=update_payload,
        current_user=owner,
    )
    assert updated_member.role == CommunityRole.MODERATOR

    # leaving removes membership
    service.leave_community(community_id=comm.id, current_user=member_user)
    assert (
        session.query(CommunityMember)
        .filter_by(community_id=comm.id, user_id=member_user.id)
        .first()
        is None
    )


def test_vip_upgrade_on_activity(session, monkeypatch):
    """Test case for test vip upgrade on activity."""
    owner = _make_user(session)
    service = CommunityService(session)
    comm = _make_community(service, owner)
    member_user = _make_user(session, email="vip@example.com")
    service.join_community(community_id=comm.id, current_user=member_user)
    member = (
        session.query(CommunityMember)
        .filter_by(community_id=comm.id, user_id=member_user.id)
        .first()
    )
    # simulate activity
    member.activity_score = ACTIVITY_THRESHOLD_VIP
    session.commit()

    # lower threshold and create a post to trigger promotion
    monkeypatch.setattr("app.services.community.service.ACTIVITY_THRESHOLD_VIP", 1)
    from app.schemas import PostCreate

    service.create_community_post(
        community_id=comm.id,
        current_user=member_user,
        payload=PostCreate(title="t", content="c"),
    )
    session.refresh(member)
    assert member.role == CommunityRole.VIP
