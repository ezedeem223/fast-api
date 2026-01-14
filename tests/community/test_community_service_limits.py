"""Test module for test community service session24."""
from datetime import datetime, timedelta, timezone

import pytest

from app import models, schemas
from app.services.community.service import CommunityService


def _user(session, email="u@example.com", verified=True):
    """Helper for  user."""
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _community_payload(name="MyCommunity", description="desc"):
    """Helper for  community payload."""
    return schemas.CommunityCreate(
        name=name, description=description, is_private=False, tags=[], rules=[]
    )


def test_create_community_limit(monkeypatch, session):
    """Test case for test create community limit."""
    service = CommunityService(session)
    user = _user(session)
    monkeypatch.setattr(service, "db", session)
    monkeypatch.setattr(
        "app.services.community.service.settings",
        type("S", (), {"MAX_OWNED_COMMUNITIES": 1})(),
    )

    service.create_community(current_user=user, payload=_community_payload("one"))
    with pytest.raises(Exception):
        service.create_community(current_user=user, payload=_community_payload("two"))


def test_create_community_duplicate_name(session):
    """Test case for test create community duplicate name."""
    service = CommunityService(session)
    user = _user(session)
    service.create_community(current_user=user, payload=_community_payload("dup"))
    with pytest.raises(Exception):
        service.create_community(current_user=user, payload=_community_payload("dup"))


def test_create_community_success_adds_owner(session):
    """Test case for test create community success adds owner."""
    service = CommunityService(session)
    user = _user(session)
    community = service.create_community(
        current_user=user, payload=_community_payload("ok")
    )
    assert community.owner_id == user.id
    assert any(
        m.user_id == user.id and m.role == models.CommunityRole.OWNER
        for m in community.members
    )


def test_join_private_requires_invitation(session):
    """Test case for test join private requires invitation."""
    service = CommunityService(session)
    owner = _user(session, "owner@example.com")
    joiner = _user(session, "joiner@example.com")
    community = service.create_community(
        current_user=owner, payload=_community_payload("private")
    )
    community.is_private = True
    session.commit()

    with pytest.raises(Exception):
        service.join_community(community_id=community.id, current_user=joiner)

    invite = models.CommunityInvitation(
        community_id=community.id, inviter_id=owner.id, invitee_id=joiner.id
    )
    session.add(invite)
    session.commit()

    result = service.join_community(community_id=community.id, current_user=joiner)
    assert "Successfully joined" in result["message"]


def test_cleanup_expired_invitations(monkeypatch, session):
    """Test case for test cleanup expired invitations."""
    service = CommunityService(session)
    user = _user(session)
    community = service.create_community(
        current_user=user, payload=_community_payload("exp")
    )
    old_invite = models.CommunityInvitation(
        community_id=community.id,
        inviter_id=user.id,
        invitee_id=user.id,
        status="pending",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(old_invite)
    session.commit()

    monkeypatch.setattr(
        "app.services.community.service.settings",
        type("S", (), {"INVITATION_EXPIRY_DAYS": 1})(),
    )
    expired = service.cleanup_expired_invitations()
    session.refresh(old_invite)
    assert expired == 1
    assert old_invite.status == "expired"


def test_update_community_requires_owner(session):
    """Test case for test update community requires owner."""
    service = CommunityService(session)
    owner = _user(session, "owner2@example.com")
    member = _user(session, "member@example.com")
    community = service.create_community(
        current_user=owner, payload=_community_payload("update")
    )
    community.members.append(
        models.CommunityMember(user_id=member.id, role=models.CommunityRole.MEMBER)
    )
    session.commit()

    with pytest.raises(Exception):
        service.update_community(
            community_id=community.id,
            payload=schemas.CommunityUpdate(name="newname"),
            current_user=member,
        )

    updated = service.update_community(
        community_id=community.id,
        payload=schemas.CommunityUpdate(name="newname"),
        current_user=owner,
    )
    assert updated.name == "newname"
