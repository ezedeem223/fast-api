from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional

router = APIRouter(prefix="/moderator", tags=["Moderator"])


async def get_current_moderator(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


@router.get("/community/{community_id}/reports", response_model=List[schemas.ReportOut])
async def get_community_reports(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
    status: Optional[str] = None,
):
    # التحقق من أن المشرف هو فعلاً مشرف في هذا المجتمع
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
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
    if status:
        query = query.filter(models.Report.status == status)
    reports = query.all()
    return reports


@router.put("/reports/{report_id}", response_model=schemas.ReportOut)
async def update_report(
    report_id: int,
    report_update: schemas.ReportUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # التحقق من أن المشرف هو فعلاً مشرف في المجتمع الذي ينتمي إليه التقرير
    post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Associated post not found")

    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == post.community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    report.status = report_update.status
    report.resolution_notes = report_update.resolution_notes
    report.reviewed_by = current_moderator.id

    db.commit()
    db.refresh(report)
    return report


@router.get(
    "/community/{community_id}/members", response_model=List[schemas.CommunityMemberOut]
)
async def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    # التحقق من أن المشرف هو فعلاً مشرف في هذا المجتمع
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    members = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .all()
    )
    return members


@router.put(
    "/community/{community_id}/member/{user_id}/role",
    response_model=schemas.CommunityMemberOut,
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.CommunityMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    # التحقق من أن المشرف هو فعلاً مشرف في هذا المجتمع
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role == models.CommunityRole.ADMIN,
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(
            status_code=403, detail="Not authorized to change roles in this community"
        )

    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this community"
        )

    member.role = role_update.role

    db.commit()
    db.refresh(member)
    return member
