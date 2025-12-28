from datetime import datetime, timedelta, timezone

import pytest

from app import models, schemas
from app.services.community import CommunityService
from app.services.community import service as community_service


def _service(session, monkeypatch):
    monkeypatch.setattr(community_service, "check_content_against_rules", lambda *a, **k: True)
    monkeypatch.setattr(community_service, "check_for_profanity", lambda *a, **k: False)
    monkeypatch.setattr(community_service, "get_translated_content", lambda content, user, lang=None: content)
    monkeypatch.setattr(community_service, "create_notification", lambda *a, **k: None)
    monkeypatch.setattr(community_service, "log_user_event", lambda *a, **k: None)
    return CommunityService(session)


def test_owner_can_promote_moderator(session, monkeypatch):
    owner = models.User(email="owner22@example.com", hashed_password="x", is_verified=True)
    member = models.User(email="member22@example.com", hashed_password="x", is_verified=True)
    community = models.Community(name="c22", description="d", owner=owner)
    session.add_all([owner, member, community])
    session.commit()
    session.refresh(owner)
    session.refresh(member)
    member_row = models.CommunityMember(user_id=member.id, community_id=community.id, role=models.CommunityRole.MEMBER)
    owner_row = models.CommunityMember(user_id=owner.id, community_id=community.id, role=models.CommunityRole.OWNER)
    session.add_all([member_row, owner_row])
    session.commit()

    svc = _service(session, monkeypatch)
    updated = svc.update_member_role(
        community_id=community.id,
        current_user=owner,
        user_id=member.id,
        new_role=models.CommunityRole.MODERATOR,
    )
    assert updated.role == models.CommunityRole.MODERATOR

    with pytest.raises(Exception):
        svc.update_member_role(
            community_id=community.id,
            current_user=member,
            user_id=owner.id,
            new_role=models.CommunityRole.MODERATOR,
        )


def test_invite_accept_decline(session, monkeypatch):
    owner = models.User(email="owner223@example.com", hashed_password="x", is_verified=True)
    invitee = models.User(email="invitee22@example.com", hashed_password="x", is_verified=True)
    community = models.Community(name="inv22", description="d", owner=owner)
    session.add_all([owner, invitee, community])
    session.commit()
    owner_member = models.CommunityMember(user_id=owner.id, community_id=community.id, role=models.CommunityRole.OWNER)
    session.add(owner_member)
    session.commit()

    svc = _service(session, monkeypatch)
    inv = svc.create_invitation(
        community_id=community.id, invited_user_id=invitee.id, inviter=owner
    )
    assert inv.community_id == community.id

    accepted = svc.accept_invitation(invitation_id=inv.id, user=invitee)
    member_row = (
        session.query(models.CommunityMember)
        .filter_by(community_id=community.id, user_id=invitee.id)
        .first()
    )
    assert member_row is not None

    non_member = models.User(email="new22@example.com", hashed_password="x", is_verified=True)
    session.add(non_member)
    session.commit()
    inv2 = svc.create_invitation(
        community_id=community.id, invited_user_id=non_member.id, inviter=owner
    )
    svc.decline_invitation(invitation_id=inv2.id, user=non_member)


def test_archive_and_unarchive(session, monkeypatch):
    owner = models.User(email="owner224@example.com", hashed_password="x", is_verified=True)
    community = models.Community(name="arch22", description="d", owner=owner)
    session.add_all([owner, community])
    session.commit()
    session.add(models.CommunityMember(user_id=owner.id, community_id=community.id, role=models.CommunityRole.OWNER))
    session.commit()

    svc = _service(session, monkeypatch)
    # owner cannot leave
    with pytest.raises(Exception):
        svc.leave_community(community_id=community.id, current_user=owner)
    # add member and allow leaving
    member = models.User(email="mem22@example.com", hashed_password="x", is_verified=True)
    session.add(member)
    session.commit()
    session.add(models.CommunityMember(user_id=member.id, community_id=community.id, role=models.CommunityRole.MEMBER))
    session.commit()
    resp = svc.leave_community(community_id=community.id, current_user=member)
    assert "left the community" in resp["message"]


def test_update_member_role_rejects_owner_role(session, monkeypatch):
    owner = models.User(email="owner22x@example.com", hashed_password="x", is_verified=True)
    member = models.User(email="member22x@example.com", hashed_password="x", is_verified=True)
    community = models.Community(name="c22x", description="d", owner=owner)
    session.add_all([owner, member, community])
    session.commit()
    session.add_all([
        models.CommunityMember(user_id=owner.id, community_id=community.id, role=models.CommunityRole.OWNER),
        models.CommunityMember(user_id=member.id, community_id=community.id, role=models.CommunityRole.MEMBER),
    ])
    session.commit()

    svc = _service(session, monkeypatch)
    with pytest.raises(Exception):
        svc.update_member_role(
            community_id=community.id,
            current_user=owner,
            user_id=member.id,
            new_role=models.CommunityRole.OWNER,
        )


def test_update_community_statistics_counts(session, monkeypatch):
    owner = models.User(email="owner22stats@example.com", hashed_password="x", is_verified=True)
    member = models.User(email="member22stats@example.com", hashed_password="x", is_verified=True)
    community = models.Community(name="c22stats", description="d", owner=owner)
    session.add_all([owner, member, community])
    session.commit()
    session.add_all([
        models.CommunityMember(user_id=owner.id, community_id=community.id, role=models.CommunityRole.OWNER),
        models.CommunityMember(user_id=member.id, community_id=community.id, role=models.CommunityRole.MEMBER),
    ])
    post = models.Post(title="p", content="c", owner=owner, community=community)
    session.add(post)
    session.commit()
    comment = models.Comment(owner_id=member.id, post_id=post.id, content="hi", language="en")
    session.add(comment)
    session.add(models.Vote(user_id=member.id, post_id=post.id))
    session.commit()

    svc = _service(session, monkeypatch)
    stats = svc.update_community_statistics(community_id=community.id)
    assert stats.member_count == 2
    assert stats.post_count == 1
    assert stats.comment_count == 1
    assert stats.total_reactions >= 1
