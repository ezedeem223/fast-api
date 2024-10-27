from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, oauth2, utils
from ..moderation import warn_user, ban_user, process_report

router = APIRouter(prefix="/moderation", tags=["Moderation"])


@router.post("/warn/{user_id}")
def warn_user_route(
    user_id: int,
    warning: schemas.WarningCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحذير مستخدم"""
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
    """حظر مستخدم"""
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
    """مراجعة تقرير"""
    if not current_user.is_moderator and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    process_report(db, report_id, review.is_valid, current_user.id)
    return {"message": "Report reviewed successfully"}


@router.post("/ip", status_code=status.HTTP_201_CREATED)
def ban_ip(
    ip_ban: schemas.IPBanCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """حظر عنوان IP"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to ban IP addresses"
        )

    existing_ban = (
        db.query(models.IPBan)
        .filter(models.IPBan.ip_address == ip_ban.ip_address)
        .first()
    )
    if existing_ban:
        raise HTTPException(status_code=400, detail="This IP address is already banned")

    new_ban = models.IPBan(**ip_ban.dict(), created_by=current_user.id)
    db.add(new_ban)
    db.commit()
    db.refresh(new_ban)

    utils.update_ban_statistics(db, "ip", ip_ban.reason, 1.0)

    return new_ban


@router.get("/ip", response_model=List[schemas.IPBanOut])
def get_banned_ips(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على قائمة عناوين IP المحظورة"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view banned IPs")

    return db.query(models.IPBan).all()


@router.delete("/ip/{ip_address}", status_code=status.HTTP_204_NO_CONTENT)
def unban_ip(
    ip_address: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إلغاء حظر عنوان IP"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to unban IP addresses"
        )

    ban = db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
    if not ban:
        raise HTTPException(status_code=404, detail="IP ban not found")

    db.delete(ban)
    db.commit()
    return {"message": "IP unbanned successfully"}
