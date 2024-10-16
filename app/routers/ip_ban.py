from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List
from datetime import datetime, timedelta

router = APIRouter(prefix="/ip-ban", tags=["IP Ban"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def ban_ip(
    ip_ban: schemas.IPBanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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

    utils.update_ban_statistics(db, "ip", ip_ban.reason, 1.0)  # افتراض فعالية أولية 1.0

    return new_ban


@router.get("/", response_model=List[schemas.IPBanOut])
def get_banned_ips(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view banned IPs")

    return db.query(models.IPBan).all()


@router.delete("/{ip_address}", status_code=status.HTTP_204_NO_CONTENT)
def unban_ip(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
