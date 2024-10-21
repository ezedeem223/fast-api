from fastapi import APIRouter, Depends, status, HTTPException, Request, BackgroundTasks
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import pyotp
from datetime import datetime, timedelta, timezone
import uuid
from jose import jwt, JWTError
from fastapi_mail import FastMail, MessageSchema
from pydantic import EmailStr

from .. import database, schemas, models, utils, oauth2
from ..config import settings
from ..notifications import send_login_notification, send_email_notification
from ..utils import log_user_event
import secrets

router = APIRouter(tags=["Authentication"])

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
TOKEN_EXPIRY = timedelta(hours=1)


@router.post("/login", response_model=schemas.Token)
def login(
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    معالجة تسجيل دخول المستخدم إلى النظام.
    """
    user = (
        db.query(models.User)
        .filter(models.User.email == user_credentials.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="بيانات الاعتماد غير صالحة"
        )

    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account is suspended")

    if user.account_locked_until and user.account_locked_until > datetime.now(
        timezone.utc
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="الحساب مقفل. حاول مرة أخرى لاحقًا.",
        )

    if not utils.verify(user_credentials.password, user.password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.account_locked_until = datetime.now(timezone.utc) + LOCKOUT_DURATION
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="بيانات الاعتماد غير صالحة"
        )

    user.failed_login_attempts = 0
    user.account_locked_until = None

    if user.is_2fa_enabled:
        return {
            "access_token": "2FA_REQUIRED",
            "token_type": "bearer",
            "user_id": user.id,
        }

    return complete_login(user, db, request, background_tasks)


@router.post("/login/2fa", response_model=schemas.Token)
def login_2fa(
    user_id: int,
    otp: schemas.Verify2FARequest,
    db: Session = Depends(database.get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    معالجة تسجيل الدخول باستخدام المصادقة الثنائية.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="طلب غير صالح")

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(otp.otp):
        raise HTTPException(status_code=400, detail="رمز OTP غير صالح")

    return complete_login(user, db, request, background_tasks)


def complete_login(user, db, request, background_tasks):
    """
    إكمال عملية تسجيل الدخول بعد المصادقة الناجحة.
    """
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

    log_user_event(
        db,
        user.id,
        "login",
        {
            "ip": request.client.host,
            "user_agent": request.headers.get("user-agent", ""),
        },
    )

    background_tasks.add_task(
        send_login_notification,
        user.email,
        request.client.host,
        request.headers.get("user-agent", ""),
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    token: str = Depends(oauth2.oauth2_scheme),
):
    """
    تسجيل خروج المستخدم من النظام.
    """
    try:
        token_data = oauth2.verify_access_token(token, None)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="توكن غير صالح"
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
        else:
            utils.log_user_event(db, current_user.id, "logout_session_not_found")

        utils.log_user_event(db, current_user.id, "logout")

        blacklist_token = models.TokenBlacklist(token=token, user_id=current_user.id)
        db.add(blacklist_token)
        db.commit()

        return {"message": "تم تسجيل الخروج بنجاح"}
    except Exception as e:
        utils.log_user_event(db, current_user.id, "logout_error", {"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="حدث خطأ أثناء تسجيل الخروج",
        )


@router.post("/logout-all-devices")
def logout_all_devices(
    current_user: models.User = Depends(oauth2.get_current_user),
    current_session: str = Depends(oauth2.get_current_session),
    db: Session = Depends(database.get_db),
):
    """
    تسجيل خروج المستخدم من جميع الأجهزة باستثناء الجهاز الحالي.
    """
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id,
        models.UserSession.session_id != current_session,
    ).delete()
    db.commit()
    log_user_event(db, current_user.id, "logout_all_devices")
    return {"message": "تم تسجيل الخروج من جميع الأجهزة الأخرى"}


@router.post("/invalidate-all-sessions")
async def invalidate_all_sessions(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "All sessions have been invalidated"}


def create_password_reset_token(email: str) -> str:
    """
    إنشاء توكن لإعادة تعيين كلمة المرور.
    """
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"exp": expire, "sub": email}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


@router.post("/reset-password-request")
async def reset_password_request(
    email: schemas.EmailSchema,
    db: Session = Depends(database.get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    معالجة طلب إعادة تعيين كلمة المرور.
    """
    user = db.query(models.User).filter(models.User.email == email.email).first()
    if user:
        token = create_password_reset_token(email.email)
        user.reset_token = token
        user.reset_token_expires = datetime.now() + TOKEN_EXPIRY
        db.commit()
        reset_link = f"https://yourapp.com/reset-password?token={token}"

        message = MessageSchema(
            subject="طلب إعادة تعيين كلمة المرور",
            recipients=[email.email],
            body=f"انقر على الرابط التالي لإعادة تعيين كلمة المرور الخاصة بك: {reset_link}",
            subtype="html",
        )

        fm = FastMail(settings.mail_config)
        background_tasks.add_task(fm.send_message, message)
        log_user_event(db, user.id, "password_reset_requested")

    return {
        "message": "If an account with that email exists, a password reset link has been sent."
    }


@router.post("/reset-password")
async def reset_password(
    reset_data: schemas.PasswordReset, db: Session = Depends(database.get_db)
):
    """
    إعادة تعيين كلمة مرور المستخدم.
    """
    try:
        payload = jwt.decode(
            reset_data.token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=400, detail="توكن غير صالح")
    except JWTError:
        raise HTTPException(status_code=400, detail="توكن غير صالح أو منتهي الصلاحية")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    if (
        not user.reset_token
        or user.reset_token != reset_data.token
        or user.reset_token_expires < datetime.now()
    ):
        raise HTTPException(status_code=400, detail="توكن غير صالح أو منتهي الصلاحية")

    hashed_password = utils.hash(reset_data.new_password)
    user.password = hashed_password
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    log_user_event(db, user.id, "password_reset_completed")

    return {"message": "تم إعادة تعيين كلمة المرور بنجاح"}


@router.post("/refresh-token", response_model=schemas.Token)
async def refresh_token(refresh_token: str, db: Session = Depends(database.get_db)):
    """
    تجديد توكن الوصول باستخدام توكن التحديث.
    """
    try:
        payload = jwt.decode(
            refresh_token, settings.refresh_secret_key, algorithms=[settings.algorithm]
        )
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="توكن التحديث غير صالح")
    except JWTError:
        raise HTTPException(status_code=401, detail="توكن التحديث غير صالح")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}
