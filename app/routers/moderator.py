"""Moderator router for handling reports review and block appeals."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.community import CommunityMember, CommunityRole
from app.modules.community.schemas import CommunityMemberOut, CommunityMemberUpdate
from fastapi import APIRouter, Depends, HTTPException

# Import project modules
from .. import models, oauth2, schemas

router = APIRouter(prefix="/moderator", tags=["Moderator"])


async def get_current_moderator(
    current_user: models.User = Depends(oauth2.get_current_user),
) -> models.User:
    """Ensure the current user has moderator privileges."""
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


@router.get("/community/{community_id}/reports", response_model=List[schemas.ReportOut])
async def get_community_reports(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
    status_filter: Optional[str] = None,
):
    """Return reports for a community, optionally filtered by status."""
    moderator_role = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.user_id == current_moderator.id,
            CommunityMember.community_id == community_id,
            CommunityMember.role.in_([CommunityRole.MODERATOR, CommunityRole.ADMIN]),
        )
        .first()
    )
    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    query = (
        db.query(models.Report)
        .join(models.Post)
        .filter(models.Post.community_id == community_id)
    )
    if status_filter:
        query = query.filter(models.Report.status == status_filter)

    return query.all()


@router.put("/reports/{report_id}", response_model=schemas.ReportOut)
async def update_report(
    report_id: int,
    report_update: schemas.ReportUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """Update a report's status and resolution notes."""
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Associated post not found")

    moderator_role = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.user_id == current_moderator.id,
            CommunityMember.community_id == post.community_id,
            CommunityMember.role.in_([CommunityRole.MODERATOR, CommunityRole.ADMIN]),
        )
        .first()
    )
    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    report.status = report_update.status
    report.resolution_notes = report_update.resolution_notes
    report.reviewed_by = current_moderator.id
    report.reviewed_at = db.func.now()  # Track when the report was reviewed.

    db.commit()
    db.refresh(report)
    return report


@router.get(
    "/community/{community_id}/members", response_model=List[CommunityMemberOut]
)
async def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """List members of a community for moderator review."""
    moderator_role = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.user_id == current_moderator.id,
            CommunityMember.community_id == community_id,
            CommunityMember.role.in_([CommunityRole.MODERATOR, CommunityRole.ADMIN]),
        )
        .first()
    )
    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    return (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id)
        .all()
    )


@router.put(
    "/community/{community_id}/member/{user_id}/role",
    response_model=CommunityMemberOut,
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: CommunityMemberUpdate,  # Use CommunityMemberUpdate for role changes.
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """Update a member's role (admin or moderator only)."""
    moderator_role = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.user_id == current_moderator.id,
            CommunityMember.community_id == community_id,
            CommunityMember.role == CommunityRole.ADMIN,
        )
        .first()
    )
    if not moderator_role:
        raise HTTPException(
            status_code=403, detail="Not authorized to change roles in this community"
        )

    member = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this community"
        )

    member.role = role_update.role
    member.updated_at = db.func.now()  # Track when the role was updated.
    member.updated_by = current_moderator.id  # Record who performed the update.

    db.commit()
    db.refresh(member)
    return member
