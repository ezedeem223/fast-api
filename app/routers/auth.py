from fastapi import APIRouter, Depends, status, HTTPException, Request, BackgroundTasks
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import pyotp
from datetime import datetime, timedelta, timezone
import uuid
from jose import jwt, JWTError
from fastapi_mail import FastMail, MessageSchema

from .. import database, schemas, models, utils, oauth2
from ..config import settings
from ..notifications import send_login_notification
from ..utils import log_user_event

router = APIRouter(tags=["Authentication"])

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


@router.post("/login", response_model=schemas.Token)
def login(
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
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

    if user.account_locked_until and user.account_locked_until > datetime.now(
        timezone.utc
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked. Try again later.",
        )

    if not utils.verify(user_credentials.password, user.password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.account_locked_until = datetime.now(timezone.utc) + LOCKOUT_DURATION
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials"
        )

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.account_locked_until = None

    if user.is_2fa_enabled:
        return {
            "access_token": "2FA_REQUIRED",
            "token_type": "bearer",
            "user_id": user.id,
        }
    log_user_event(
        db,
        user.id,
        "login",
        {
            "ip": request.client.host,
            "user_agent": request.headers.get("user-agent", ""),
        },
    )

    user.last_login = datetime.now(timezone.utc)
    session = models.UserSession(
        user_id=user.id,
        session_id=str(uuid.uuid4()),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
    )
    db.add(session)
    db.commit()

    access_token = oauth2.create_access_token(
        data={"user_id": user.id, "session_id": session.session_id}
    )

    # Send login notification
    background_tasks.add_task(
        send_login_notification,
        user.email,
        request.client.host,
        request.headers.get("user-agent", ""),
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login/2fa", response_model=schemas.Token)
def login_2fa(
    user_id: int,
    otp: schemas.Verify2FARequest,
    db: Session = Depends(database.get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="Invalid request")

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(otp.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user.last_login = datetime.now(timezone.utc)
    session = models.UserSession(
        user_id=user.id,
        session_id=str(uuid.uuid4()),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
    )
    db.add(session)
    db.commit()

    access_token = oauth2.create_access_token(
        data={"user_id": user.id, "session_id": session.session_id}
    )

    # Send login notification
    background_tasks.add_task(
        send_login_notification,
        user.email,
        request.client.host,
        request.headers.get("user-agent", ""),
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    token: str = Depends(oauth2.oauth2_scheme),
):
    token_data = oauth2.verify_access_token(
        token, HTTPException(status_code=401, detail="Invalid token")
    )
    session = (
        db.query(models.UserSession)
        .filter(
            models.UserSession.user_id == current_user.id,
            models.UserSession.session_id == token_data.session_id,
        )
        .first()
    )

    if session:
        db.delete(session)
        db.commit()
    log_user_event(db, current_user.id, "logout")
    return {"message": "Logged out successfully"}


@router.post("/logout-all-devices")
def logout_all_devices(
    current_user: models.User = Depends(oauth2.get_current_user),
    current_session: str = Depends(oauth2.get_current_session),
    db: Session = Depends(database.get_db),
):
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id,
        models.UserSession.session_id != current_session,
    ).delete()
    db.commit()
    return {"message": "Logged out from all other devices"}


def create_password_reset_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"exp": expire, "email": email}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


@router.post("/reset-password-request")
async def reset_password_request(
    email: schemas.EmailSchema,
    db: Session = Depends(database.get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    user = db.query(models.User).filter(models.User.email == email.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    token = create_password_reset_token(email.email)
    reset_link = f"https://yourapp.com/reset-password?token={token}"

    message = MessageSchema(
        subject="Password Reset Request",
        recipients=[email.email],
        body=f"Click the following link to reset your password: {reset_link}",
        subtype="html",
    )

    fm = FastMail(settings.mail_config)
    background_tasks.add_task(fm.send_message, message)

    return {"message": "Password reset instructions sent to your email"}


@router.post("/reset-password")
async def reset_password(
    reset_data: schemas.PasswordReset, db: Session = Depends(database.get_db)
):
    try:
        payload = jwt.decode(
            reset_data.token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("email")
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = utils.hash(reset_data.new_password)
    user.password = hashed_password
    db.commit()

    return {"message": "Password reset successfully"}
