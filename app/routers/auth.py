from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .. import database, schemas, models, utils, oauth2

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=schemas.Token)
def login(
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    user = (
        db.query(models.User)
        .filter(models.User.email == user_credentials.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials"
        )
    if not utils.verify(user_credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials"
        )
    # إنشاء التوكن
    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify_2fa")
def verify_2fa(
    otp: str,
    db: Session = Depends(database.get_db),  # هنا تم التصحيح
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled for this user.")

    totp = pyotp.TOTP(current_user.otp_secret)
    if not totp.verify(otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    return {"message": "2FA verified successfully"}
