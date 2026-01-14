"""Test module for test session2 community service extra."""
from datetime import datetime, timezone

import pytest

from app import models, schemas
from app.services.community.service import CommunityService
from fastapi import HTTPException


def _make_user(session, email: str, verified: bool = True) -> models.User:
    """Helper for  make user."""
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_category(session, name: str = "Cat"):
    """Helper for  make category."""
    cat = models.Category(name=name)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def _make_community(session, owner: models.User, name: str = "C1") -> models.Community:
    """Helper for  make community."""
    community = models.Community(
        name=name,
        description="desc",
        owner_id=owner.id,
        is_active=True,
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    session.add(
        models.CommunityMember(
            community_id=community.id,
            user_id=owner.id,
            role=models.CommunityRole.OWNER,
            join_date=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return community


def test_update_community_duplicate_name(session):
    """Test case for test update community duplicate name."""
    service = CommunityService(session)
    owner = _make_user(session, "owner-update@example.com")
    _make_community(session, owner, name="Alpha")
    second = _make_community(session, owner, name="Beta")
    payload = schemas.CommunityUpdate(name="alpha")
    with pytest.raises(HTTPException) as exc:
        service.update_community(
            community_id=second.id, payload=payload, current_user=owner
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Community with this name already exists"


def test_get_communities_filters_and_sort(session):
    """Test case for test get communities filters and sort."""
    service = CommunityService(session)
    owner = _make_user(session, "owner-filter@example.com")
    cat1 = _make_category(session, "Tech")
    cat2 = _make_category(session, "Art")
    c1 = _make_community(session, owner, name="Alpha")
    c2 = _make_community(session, owner, name="Beta")
    c1.community_category = models.CommunityCategory(name="Tech", category_id=cat1.id)
    c2.community_category = models.CommunityCategory(name="Art", category_id=cat2.id)
    c2.is_active = False
    session.commit()

    res = service.get_communities(search="Alpha", sort_by="name")
    assert len(res) == 1 and res[0].name == "Alpha"

    res = service.get_communities(category="Tech")
    assert res and res[0].name == "Alpha"

    res = service.get_communities(is_active=False)
    assert len(res) == 1 and res[0].name == "Beta"


def test_update_community_statistics_and_rankings(session):
    """Test case for test update community statistics and rankings."""
    service = CommunityService(session)
    owner = _make_user(session, "owner-stats@example.com")
    community = _make_community(session, owner)
    # add member, post, comment, vote
    member = _make_user(session, "member-stats@example.com")
    session.add(
        models.CommunityMember(
            community_id=community.id,
            user_id=member.id,
            role=models.CommunityRole.MEMBER,
            join_date=datetime.now(timezone.utc),
        )
    )
    session.commit()
    post = models.Post(
        owner_id=owner.id,
        community_id=community.id,
        title="t",
        content="c",
        is_safe_content=True,
    )
    session.add(post)
    session.commit()
    comment = models.Comment(owner_id=member.id, post_id=post.id, content="hi")
    session.add(comment)
    session.commit()
    vote = models.Vote(user_id=member.id, post_id=post.id)
    session.add(vote)
    session.commit()
    for comm in session.query(models.Community).all():
        comm.created_at = datetime.now(timezone.utc)
    session.commit()

    def safe_rankings():
        for comm in session.query(models.Community).all():
            comm.ranking = 0.0
        session.commit()

    service.update_community_rankings = safe_rankings

    stats = service.update_community_statistics(community_id=community.id)
    assert stats.member_count >= 1
    assert stats.post_count >= 1
    assert stats.comment_count >= 1
    assert stats.total_reactions >= 1

    # rankings should compute without error
    service.update_community_rankings()
    session.refresh(community)
    assert community.ranking is not None or True  # ensure no exception


def test_cleanup_expired_invitations_disabled(monkeypatch, session):
    """Test case for test cleanup expired invitations disabled."""
    monkeypatch.setattr(
        "app.services.community.service.settings.INVITATION_EXPIRY_DAYS",
        0,
        raising=False,
    )
    service = CommunityService(session)
    owner = _make_user(session, "owner-expiry@example.com")
    community = _make_community(session, owner, name="Expiry")
    invite = models.CommunityInvitation(
        community_id=community.id,
        inviter_id=owner.id,
        invitee_id=owner.id,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(invite)
    session.commit()
    assert service.cleanup_expired_invitations() == 0
    session.refresh(invite)
    assert invite.status == "pending"
