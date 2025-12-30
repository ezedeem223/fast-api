import pytest

from app import models, schemas
from app.modules.community.models import Community, CommunityRole
from app.services.community.service import CommunityService
from fastapi import HTTPException


def _make_user(session, email="u@example.com", verified=True):
    user = models.User(
        email=email,
        hashed_password="hashed",
        is_verified=verified,
    )
    session.add(user)
    session.commit()
    return user


def test_create_community_success(session):
    user = _make_user(session)
    service = CommunityService(session)
    payload = schemas.CommunityCreate(name="Test Community", description="desc")
    community = service.create_community(current_user=user, payload=payload)

    assert community.owner_id == user.id
    assert any(member.role == CommunityRole.OWNER for member in community.members)
    # ensure persisted
    fetched = session.get(Community, community.id)
    assert fetched is not None


def test_create_community_unverified_rejected(session):
    user = _make_user(session, verified=False)
    service = CommunityService(session)
    payload = schemas.CommunityCreate(name="Blocked", description=None)
    with pytest.raises(HTTPException) as exc:
        service.create_community(current_user=user, payload=payload)
    assert exc.value.status_code == 403


def test_create_community_respects_owned_limit(session, monkeypatch):
    user = _make_user(session)
    service = CommunityService(session)
    from app.core import config

    monkeypatch.setattr(config.settings, "MAX_OWNED_COMMUNITIES", 1)
    payload = schemas.CommunityCreate(name="First", description=None)
    service.create_community(current_user=user, payload=payload)

    payload2 = schemas.CommunityCreate(name="Second", description=None)
    with pytest.raises(HTTPException) as exc:
        service.create_community(current_user=user, payload=payload2)
    assert exc.value.status_code == 400


def test_get_communities_filters_and_sorts(session):
    user = _make_user(session)
    service = CommunityService(session)
    payload_a = schemas.CommunityCreate(name="Alpha club", description=None)
    payload_b = schemas.CommunityCreate(name="Beta group", description=None)
    service.create_community(current_user=user, payload=payload_a)
    service.create_community(current_user=user, payload=payload_b)

    results = service.get_communities(search="Alpha")
    assert len(results) == 1
    assert results[0].name == "Alpha club"

    sorted_results = service.get_communities(sort_by="name", order="asc")
    names = [c.name for c in sorted_results]
    assert names == sorted(names)
