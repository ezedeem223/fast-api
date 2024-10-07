from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import pyotp
from .. import models, database, oauth2, schemas
from ..utils import generate_qr_code

router = APIRouter(prefix="/2fa", tags=["Two Factor Authentication"])


@router.post("/enable", response_model=schemas.Enable2FAResponse)
def enable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.is_2fa_enabled:
        raise HTTPException(
            status_code=400, detail="Two-factor authentication is already enabled."
        )

    secret = pyotp.random_base32()
    current_user.otp_secret = secret
    current_user.is_2fa_enabled = True
    db.commit()

    totp = pyotp.TOTP(secret)
    qr_code = generate_qr_code(
        totp.provisioning_uri(current_user.email, issuer_name="YourAppName")
    )

    return {"otp_secret": secret, "qr_code": qr_code}


@router.post("/disable")
def disable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    if not current_user.is_2fa_enabled:
        raise HTTPException(
            status_code=400, detail="Two-factor authentication is not enabled."
        )

    current_user.otp_secret = None
    current_user.is_2fa_enabled = False
    db.commit()

    return {"message": "Two-factor authentication has been disabled."}


@router.post("/verify", response_model=schemas.Verify2FAResponse)
def verify_2fa(
    otp: schemas.Verify2FARequest,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    if not current_user.is_2fa_enabled or not current_user.otp_secret:
        raise HTTPException(
            status_code=400,
            detail="Two-factor authentication is not enabled for this user.",
        )

    totp = pyotp.TOTP(current_user.otp_secret)
    if not totp.verify(otp.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    return {"message": "OTP verified successfully"}
