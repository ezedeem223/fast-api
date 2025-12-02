from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.oauth2 import get_current_user
from app import models
from app.modules.collaboration.models import CollaborativeProject, ProjectContribution
from app.modules.collaboration.schemas import (
    ProjectCreate,
    ProjectOut,
    ContributionCreate,
    ContributionOut,
    ProjectWithContributions,
)

router = APIRouter(prefix="/collaboration", tags=["Collaboration"])


@router.post("/projects", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = CollaborativeProject(
        title=payload.title,
        description=payload.description,
        goals=payload.goals,
        owner_id=current_user.id,
        community_id=payload.community_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=List[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    projects = (
        db.query(CollaborativeProject)
        .filter(CollaborativeProject.owner_id == current_user.id)
        .all()
    )
    return projects


@router.get(
    "/projects/{project_id}",
    response_model=ProjectWithContributions,
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(CollaborativeProject)
        .filter(
            CollaborativeProject.id == project_id,
            CollaborativeProject.owner_id == current_user.id,
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/contributions",
    response_model=ContributionOut,
    status_code=201,
)
def add_contribution(
    project_id: int,
    payload: ContributionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = db.query(CollaborativeProject).filter(CollaborativeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    contribution = ProjectContribution(
        project_id=project_id,
        user_id=current_user.id,
        content=payload.content,
        contribution_type=payload.contribution_type,
    )
    db.add(contribution)
    db.commit()
    db.refresh(contribution)
    return contribution


@router.get(
    "/projects/{project_id}/contributions",
    response_model=List[ContributionOut],
)
def list_contributions(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = db.query(CollaborativeProject).filter(CollaborativeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    contributions = (
        db.query(ProjectContribution)
        .filter(ProjectContribution.project_id == project_id)
        .order_by(ProjectContribution.created_at.asc())
        .all()
    )
    return contributions
