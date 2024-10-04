from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List

router = APIRouter(prefix="/admin", tags=["Admin"])


async def get_current_admin(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


@router.get("/stats")
def get_statistics(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    try:
        post_count = db.query(models.Post).count()
        user_count = db.query(models.User).count()
        report_count = db.query(models.Report).count()
        community_count = db.query(models.Community).count()

        return {
            "total_posts": post_count,
            "total_users": user_count,
            "total_reports": report_count,
            "total_communities": community_count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching statistics.",
        )


@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
    skip: int = 0,
    limit: int = 100,
):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


@router.put("/users/{user_id}/role", response_model=schemas.UserOut)
async def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_moderator = role_update.is_moderator
    user.is_admin = role_update.is_admin

    db.commit()
    db.refresh(user)
    return user


@router.get("/reports/overview")
async def get_reports_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    total_reports = db.query(models.Report).count()
    pending_reports = (
        db.query(models.Report).filter(models.Report.status == "pending").count()
    )
    resolved_reports = (
        db.query(models.Report).filter(models.Report.status == "resolved").count()
    )

    return {
        "total_reports": total_reports,
        "pending_reports": pending_reports,
        "resolved_reports": resolved_reports,
    }


@router.get("/communities/overview")
async def get_communities_overview(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    total_communities = db.query(models.Community).count()
    active_communities = (
        db.query(models.Community).filter(models.Community.is_active == True).count()
    )

    return {
        "total_communities": total_communities,
        "active_communities": active_communities,
    }
