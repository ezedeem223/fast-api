"""Two-factor auth router (OTP setup/verification) for account security."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import pyotp
import logging
from .. import models, oauth2, schemas
from app.core.database import get_db
from app.modules.utils.files import generate_qr_code

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/2fa",
    tags=["Two Factor Authentication"],
    responses={
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Internal Server Error"},
    },
)


class TwoFactorAuth:
    """Class to manage two-factor authentication operations."""

    @staticmethod
    def generate_secret() -> str:
        """Endpoint: generate_secret."""
        return pyotp.random_base32()

    @staticmethod
    def verify_totp(secret: str, otp: str) -> bool:
        """Endpoint: verify_totp."""
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(otp)
        except Exception as e:
            logger.error(f"Error verifying TOTP: {str(e)}")
            return False

    @staticmethod
    def generate_provisioning_uri(secret: str, email: str) -> str:
        """Endpoint: generate_provisioning_uri."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(email, issuer_name="YourAppName")


@router.post("/enable", response_model=schemas.Enable2FAResponse)
async def enable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
) -> schemas.Enable2FAResponse:
    """
    Enable two-factor authentication for the current user.

    Returns:
        Enable2FAResponse: Contains the TOTP secret and the QR code.

    Raises:
        HTTPException: If 2FA is already enabled or on error.
    """
    try:
        if current_user.is_2fa_enabled:
            raise HTTPException(
                status_code=400, detail="Two-factor authentication is already enabled."
            )

        # Generate a new TOTP secret
        secret = TwoFactorAuth.generate_secret()

        # Update user settings
        current_user.otp_secret = secret
        current_user.is_2fa_enabled = True
        db.commit()

        # Generate provisioning URI and QR code
        provisioning_uri = TwoFactorAuth.generate_provisioning_uri(
            secret, current_user.email
        )
        qr_code = generate_qr_code(provisioning_uri)

        return {"otp_secret": secret, "qr_code": qr_code}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling 2FA: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Error enabling two-factor authentication"
        )


@router.post("/disable")
async def disable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Disable two-factor authentication for the current user.

    Returns:
        dict: A success message.

    Raises:
        HTTPException: If 2FA is not enabled or on error.
    """
    try:
        if not current_user.is_2fa_enabled:
            raise HTTPException(
                status_code=400, detail="Two-factor authentication is not enabled."
            )

        current_user.otp_secret = None
        current_user.is_2fa_enabled = False
        db.commit()

        return {"message": "Two-factor authentication has been disabled."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling 2FA: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Error disabling two-factor authentication"
        )


@router.post("/verify", response_model=schemas.Verify2FAResponse)
async def verify_2fa(
    otp: schemas.Verify2FARequest,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
) -> schemas.Verify2FAResponse:
    """
    Verify the provided OTP for two-factor authentication.

    Returns:
        Verify2FAResponse: A success message if OTP is valid.

    Raises:
        HTTPException: If 2FA is not enabled or OTP is invalid.
    """
    try:
        if not current_user.is_2fa_enabled or not current_user.otp_secret:
            raise HTTPException(
                status_code=400,
                detail="Two-factor authentication is not enabled for this user.",
            )

        if not TwoFactorAuth.verify_totp(current_user.otp_secret, otp.otp):
            raise HTTPException(status_code=400, detail="Invalid OTP")

        return {"message": "OTP verified successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying 2FA: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error verifying two-factor authentication"
        )
