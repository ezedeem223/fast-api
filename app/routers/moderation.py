from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import database, models, schemas, oauth2
from ..moderation import warn_user, ban_user

router = APIRouter(prefix="/moderation", tags=["Moderation"])


@router.post("/warn/{user_id}")
def warn_user_route(
    user_id: int,
    warning: schemas.WarningCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    warn_user(db, user_id, warning.reason)
    return {"message": "User warned successfully"}


@router.post("/ban/{user_id}")
def ban_user_route(
    user_id: int,
    ban: schemas.BanCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    ban_user(db, user_id, ban.reason)
    return {"message": "User banned successfully"}


@router.put("/reports/{report_id}/review")
def review_report(
    report_id: int,
    review: schemas.ReportReview,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    process_report(db, report_id, review.is_valid, current_user.id)
    return {"message": "Report reviewed successfully"}
