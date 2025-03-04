from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import timedelta

# Import project modules
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/moderator", tags=["Moderator"])

# ─── Authentication ─────────────────────────────────────────────────────────────


async def get_current_moderator(
    current_user: models.User = Depends(oauth2.get_current_user),
) -> models.User:
    """
    Verify that the current user has moderator privileges.

    Parameters:
        current_user (models.User): The currently authenticated user.

    Returns:
        models.User: The user if they have moderator privileges.

    Raises:
        HTTPException: If the user is not a moderator.
    """
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


# ─── Report Management ─────────────────────────────────────────────────────────


@router.get("/community/{community_id}/reports", response_model=List[schemas.ReportOut])
async def get_community_reports(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
    status_filter: Optional[str] = None,
):
    """
    Retrieve reports for a specific community.

    Parameters:
        community_id (int): The ID of the community.
        db (Session): Database session.
        current_moderator (models.User): The current moderator.
        status_filter (Optional[str]): Filter reports by status (optional).

    Returns:
        List[schemas.ReportOut]: List of reports for the community.

    Raises:
        HTTPException: If the moderator is not authorized for the community.
    """
    # Verify moderator's role in the community
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
    """
    Update a report's status and resolution notes.

    Parameters:
        report_id (int): The ID of the report to update.
        report_update (schemas.ReportUpdate): The update data.
        db (Session): Database session.
        current_moderator (models.User): The current moderator.

    Returns:
        schemas.ReportOut: The updated report.

    Raises:
        HTTPException: If the report or associated post is not found,
                       or if the moderator is not authorized for the community.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Verify associated post exists
    post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Associated post not found")

    # Check moderator's role in the community of the post
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
    report.reviewed_at = db.func.now()  # Update the reviewed_at timestamp

    db.commit()
    db.refresh(report)
    return report


# ─── Community Members Management ─────────────────────────────────────────────


@router.get(
    "/community/{community_id}/members", response_model=List[schemas.CommunityMemberOut]
)
async def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """
    Retrieve community members for a given community.

    Parameters:
        community_id (int): The ID of the community.
        db (Session): Database session.
        current_moderator (models.User): The current moderator.

    Returns:
        List[schemas.CommunityMemberOut]: List of community members.

    Raises:
        HTTPException: If the moderator is not authorized for the community.
    """
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

    return (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .all()
    )


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
    """
    Update a community member's role.

    Parameters:
        community_id (int): The ID of the community.
        user_id (int): The ID of the member whose role is to be updated.
        role_update (schemas.CommunityMemberRoleUpdate): The new role data.
        db (Session): Database session.
        current_moderator (models.User): The current moderator.

    Returns:
        schemas.CommunityMemberOut: The updated community member record.

    Raises:
        HTTPException: If the moderator is not authorized to change roles or if the member is not found.
    """
    # Only an admin can change roles in a community.
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
    member.updated_at = db.func.now()  # Optionally update the last updated timestamp
    member.updated_by = current_moderator.id  # Track who made the update

    db.commit()
    db.refresh(member)
    return member
