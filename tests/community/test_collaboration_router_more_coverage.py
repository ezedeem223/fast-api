"""Additional coverage for collaboration router branches."""

import pytest
from fastapi import HTTPException

from app import models
from app.modules.collaboration.models import CollaborativeProject
from app.modules.collaboration.schemas import ContributionCreate
from app.routers import collaboration as collaboration_router


def _user(session, email):
    """Helper to create a user."""
    user = models.User(email=email, hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_collaboration_list_projects_filters_by_owner(session):
    """Ensure list_projects returns only owner projects."""
    owner = _user(session, "owner_collab@example.com")
    other = _user(session, "other_collab@example.com")

    owner_project = CollaborativeProject(
        title="Owner Project",
        description="d",
        goals="g",
        owner_id=owner.id,
    )
    other_project = CollaborativeProject(
        title="Other Project",
        description="d",
        goals="g",
        owner_id=other.id,
    )
    session.add_all([owner_project, other_project])
    session.commit()

    projects = collaboration_router.list_projects(
        db=session, current_user=owner, skip=0, limit=20
    )
    assert [project.id for project in projects] == [owner_project.id]


def test_collaboration_not_found_branches(session):
    """Cover not-found branches for project and contributions."""
    owner = _user(session, "missing_collab@example.com")

    with pytest.raises(HTTPException) as exc:
        collaboration_router.get_project(
            project_id=999, db=session, current_user=owner
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Project not found"

    payload = ContributionCreate(content="c", contribution_type="text")
    with pytest.raises(HTTPException) as exc:
        collaboration_router.add_contribution(
            project_id=999, payload=payload, db=session, current_user=owner
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Project not found"

    with pytest.raises(HTTPException) as exc:
        collaboration_router.list_contributions(
            project_id=999, db=session, current_user=owner, skip=0, limit=10
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Project not found"
