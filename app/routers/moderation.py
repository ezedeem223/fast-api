"""Moderation router for warnings, bans, IP bans, and block appeals."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

# Import project modules
from .. import models, schemas, oauth2
from app.core.database import get_db
from app.modules.moderation.service import warn_user, ban_user, process_report
from app.modules.utils.analytics import update_ban_statistics

# Configure the moderation router
router = APIRouter(prefix="/moderation", tags=["Moderation"])

# Constants for report handling
REPORT_THRESHOLD = 5  # Number of reports before automatic ban
REPORT_WINDOW = timedelta(days=30)  # Time window to consider reports


@router.post("/warn/{user_id}")
def warn_user_route(
    user_id: int,
    warning: schemas.WarningCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Warn a user.

    Parameters:
        user_id: ID of the user to be warned.
        warning: Warning details containing the reason.
        db: Database session.
        current_user: The current moderator or admin user.

    Raises:
        HTTPException: If the current user is not authorized.

    Returns:
        A success message if the user is warned successfully.
    """
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    warn_user(db, user_id, warning.reason)
    return {"message": "User warned successfully"}


@router.post("/ban/{user_id}")
def ban_user_route(
    user_id: int,
    ban: schemas.BanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Ban a user.

    Parameters:
        user_id: ID of the user to be banned.
        ban: Ban details containing the reason.
        db: Database session.
        current_user: The current moderator or admin user.

    Raises:
        HTTPException: If the current user is not authorized.

    Returns:
        A success message if the user is banned successfully.
    """
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    ban_user(db, user_id, ban.reason)
    return {"message": "User banned successfully"}


@router.put("/reports/{report_id}/review")
def review_report(
    report_id: int,
    review: schemas.ReportReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Review a report submitted by users.

    Parameters:
        report_id: ID of the report to review.
        review: Review details (validity of the report).
        db: Database session.
        current_user: The current moderator or admin user.

    Raises:
        HTTPException: If the current user is not authorized.

    Returns:
        A success message if the report is reviewed successfully.
    """
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    process_report(db, report_id, review.is_valid, current_user.id)
    return {"message": "Report reviewed successfully"}


@router.post("/ip", status_code=status.HTTP_201_CREATED)
def ban_ip(
    ip_ban: schemas.IPBanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Ban an IP address.

    Parameters:
        ip_ban: IP ban details including the IP address and reason.
        db: Database session.
        current_user: The current admin user.

    Raises:
        HTTPException: If the current user is not an admin or if the IP is already banned.

    Returns:
        The newly created IP ban record.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to ban IP addresses"
        )

    # Check if the IP is already banned
    existing_ban = (
        db.query(models.IPBan)
        .filter(models.IPBan.ip_address == ip_ban.ip_address)
        .first()
    )
    if existing_ban:
        raise HTTPException(status_code=400, detail="This IP address is already banned")

    # Create a new IP ban record
    new_ban = models.IPBan(**ip_ban.dict(), created_by=current_user.id)
    db.add(new_ban)
    db.commit()
    db.refresh(new_ban)

    # Update ban statistics using utility function
    update_ban_statistics(db, "ip", ip_ban.reason, 1.0)

    return new_ban


@router.get("/ip", response_model=List[schemas.IPBanOut])
def get_banned_ips(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve a list of banned IP addresses.

    Parameters:
        db: Database session.
        current_user: The current admin user.

    Raises:
        HTTPException: If the current user is not authorized.

    Returns:
        A list of IP ban records.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view banned IPs")

    return db.query(models.IPBan).all()


@router.delete("/ip/{ip_address}", status_code=status.HTTP_204_NO_CONTENT)
def unban_ip(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Unban an IP address.

    Parameters:
        ip_address: The IP address to unban.
        db: Database session.
        current_user: The current admin user.

    Raises:
        HTTPException: If the current user is not authorized or if the IP ban is not found.

    Returns:
        A message indicating successful unbanning.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to unban IP addresses"
        )

    # Locate the existing ban record for the given IP
    ban = db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
    if not ban:
        raise HTTPException(status_code=404, detail="IP ban not found")

    db.delete(ban)
    db.commit()
    return {"message": "IP unbanned successfully"}
