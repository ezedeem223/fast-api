from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import pyotp
from .. import models, database, oauth2

router = APIRouter(prefix="/2fa", tags=["Two Factor Authentication"])


@router.post("/enable")
def enable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    # توليد سر 2FA جديد
    secret = pyotp.random_base32()

    # تحديث المستخدم بحفظ السر في قاعدة البيانات
    current_user.otp_secret = secret
    db.commit()

    # إرجاع السر أو URI لإنشاء QR code باستخدام Google Authenticator أو أي تطبيق 2FA آخر
    otp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        current_user.email, issuer_name="YourAppName"
    )

    return {"otp_uri": otp_uri, "secret": secret}
