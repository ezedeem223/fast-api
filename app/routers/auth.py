"""
Authentication Router Module
يوفر نقاط النهاية الخاصة بالمصادقة وإدارة الجلسات
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import uuid
from typing import Optional
import pyotp
from jose import jwt, JWTError
from fastapi_mail import FastMail, MessageSchema
from pydantic import EmailStr

from .. import database, schemas, models, utils, oauth2
from ..config import settings
from ..notifications import send_login_notification, send_email_notification
from ..utils import log_user_event

router = APIRouter(tags=["Authentication"])

# ثوابت المصادقة
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
    تسجيل دخول المستخدم

    Parameters:
        user_credentials: بيانات اعتماد المستخدم
        db: جلسة قاعدة البيانات
        request: طلب HTTP
        background_tasks: مهام خلفية

    Returns:
        Token: رمز الوصول
    """
    # التحقق من وجود المستخدم
    user = (
        db.query(models.User)
        .filter(models.User.email == user_credentials.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="بيانات الاعتماد غير صالحة"
        )

    # التحقق من حالة الحساب
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="الحساب موقوف")

    if user.account_locked_until and user.account_locked_until > datetime.now(
        timezone.utc
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="الحساب مقفل. حاول مرة أخرى لاحقاً",
        )

    # التحقق من كلمة المرور
    if not utils.verify(user_credentials.password, user.password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.account_locked_until = datetime.now(timezone.utc) + LOCKOUT_DURATION
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="بيانات الاعتماد غير صالحة"
        )

    # إعادة تعيين عدادات الفشل
    user.failed_login_attempts = 0
    user.account_locked_until = None

    # التحقق من المصادقة الثنائية
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
    تسجيل الدخول باستخدام المصادقة الثنائية

    Parameters:
        user_id: معرف المستخدم
        otp: رمز التحقق
        db: جلسة قاعدة البيانات
        request: طلب HTTP
        background_tasks: مهام خلفية

    Returns:
        Token: رمز الوصول
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="طلب غير صالح")

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(otp.otp):
        raise HTTPException(status_code=400, detail="رمز OTP غير صالح")

    return complete_login(user, db, request, background_tasks)


def complete_login(
    user: models.User, db: Session, request: Request, background_tasks: BackgroundTasks
) -> dict:
    """
    إكمال عملية تسجيل الدخول

    Parameters:
        user: المستخدم
        db: جلسة قاعدة البيانات
        request: طلب HTTP
        background_tasks: مهام خلفية

    Returns:
        dict: رمز الوصول ونوعه
    """
    # تحديث بيانات آخر تسجيل دخول
    user.last_login = datetime.now(timezone.utc)

    # إنشاء جلسة جديدة
    session = models.UserSession(
        user_id=user.id,
        session_id=str(uuid.uuid4()),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
    )
    db.add(session)
    db.commit()

    # إنشاء رمز الوصول
    access_token = oauth2.create_access_token(
        data={"user_id": user.id, "session_id": session.session_id}
    )

    # تسجيل الحدث
    log_user_event(
        db,
        user.id,
        "login",
        {
            "ip": request.client.host,
            "user_agent": request.headers.get("user-agent", ""),
        },
    )

    # إرسال إشعار تسجيل الدخول
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
    تسجيل خروج المستخدم

    Parameters:
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي
        token: رمز الوصول
    """
    try:
        # التحقق من صحة الرمز
        token_data = oauth2.verify_access_token(token, None)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="رمز غير صالح"
            )

        # إنهاء الجلسة
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

        # تسجيل حدث تسجيل الخروج
        utils.log_user_event(db, current_user.id, "logout")

        # إضافة الرمز إلى القائمة السوداء
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
    تسجيل خروج المستخدم من جميع الأجهزة باستثناء الجهاز الحالي
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
    """إبطال جميع الجلسات"""
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "تم إبطال جميع الجلسات"}


def create_password_reset_token(email: str) -> str:
    """إنشاء رمز إعادة تعيين كلمة المرور"""
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
    طلب إعادة تعيين كلمة المرور
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
        "message": "إذا كان هناك حساب بهذا البريد الإلكتروني، سيتم إرسال رابط إعادة تعيين كلمة المرور"
    }


@router.post("/reset-password")
async def reset_password(
    reset_data: schemas.PasswordReset,
    db: Session = Depends(database.get_db),
):
    """
    إعادة تعيين كلمة المرور
    """
    try:
        payload = jwt.decode(
            reset_data.token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=400, detail="رمز غير صالح")
    except JWTError:
        raise HTTPException(status_code=400, detail="رمز غير صالح أو منتهي الصلاحية")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    if (
        not user.reset_token
        or user.reset_token != reset_data.token
        or user.reset_token_expires < datetime.now()
    ):
        raise HTTPException(status_code=400, detail="رمز غير صالح أو منتهي الصلاحية")

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
    تجديد رمز الوصول باستخدام رمز التحديث
    """
    try:
        payload = jwt.decode(
            refresh_token, settings.refresh_secret_key, algorithms=[settings.algorithm]
        )
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="رمز التحديث غير صالح")
    except JWTError:
        raise HTTPException(status_code=401, detail="رمز التحديث غير صالح")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify-email")
async def verify_email(token: str, db: Session = Depends(database.get_db)):
    """
    التحقق من البريد الإلكتروني

    Parameters:
        token: رمز التحقق
        db: جلسة قاعدة البيانات
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=400, detail="رمز غير صالح")
    except JWTError:
        raise HTTPException(status_code=400, detail="رمز غير صالح أو منتهي الصلاحية")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    user.is_verified = True
    db.commit()
    log_user_event(db, user.id, "email_verified")

    return {"message": "تم التحقق من البريد الإلكتروني بنجاح"}


@router.post("/resend-verification")
async def resend_verification_email(
    email: schemas.EmailSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    """
    إعادة إرسال رابط التحقق من البريد الإلكتروني

    Parameters:
        email: نموذج البريد الإلكتروني
        background_tasks: مهام خلفية
        db: جلسة قاعدة البيانات
    """
    user = db.query(models.User).filter(models.User.email == email.email).first()
    if user and not user.is_verified:
        token = create_verification_token(email.email)
        verification_link = f"https://yourapp.com/verify-email?token={token}"

        message = MessageSchema(
            subject="تأكيد البريد الإلكتروني",
            recipients=[email.email],
            body=f"انقر على الرابط التالي لتأكيد بريدك الإلكتروني: {verification_link}",
            subtype="html",
        )

        fm = FastMail(settings.mail_config)
        background_tasks.add_task(fm.send_message, message)
        log_user_event(db, user.id, "verification_email_resent")

    return {"message": "إذا كان الحساب موجوداً وغير مؤكد، سيتم إرسال رابط التحقق"}


@router.post("/change-email")
async def change_email(
    email_change: schemas.EmailChange,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    تغيير البريد الإلكتروني للمستخدم

    Parameters:
        email_change: نموذج تغيير البريد الإلكتروني
        current_user: المستخدم الحالي
        db: جلسة قاعدة البيانات
    """
    # التحقق من كلمة المرور
    if not utils.verify(email_change.password, current_user.password):
        raise HTTPException(status_code=400, detail="كلمة المرور غير صحيحة")

    # التحقق من عدم استخدام البريد الإلكتروني من قبل مستخدم آخر
    existing_user = (
        db.query(models.User)
        .filter(models.User.email == email_change.new_email)
        .first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مستخدم بالفعل")

    # تحديث البريد الإلكتروني
    current_user.email = email_change.new_email
    current_user.is_verified = False
    db.commit()

    log_user_event(
        db,
        current_user.id,
        "email_changed",
        {"old_email": email_change.old_email, "new_email": email_change.new_email},
    )

    return {"message": "تم تغيير البريد الإلكتروني بنجاح"}


@router.post("/sessions/active", response_model=List[schemas.UserSessionOut])
async def get_active_sessions(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    الحصول على قائمة الجلسات النشطة للمستخدم

    Parameters:
        current_user: المستخدم الحالي
        db: جلسة قاعدة البيانات
    """
    sessions = (
        db.query(models.UserSession)
        .filter(models.UserSession.user_id == current_user.id)
        .order_by(models.UserSession.last_activity.desc())
        .all()
    )
    return sessions


@router.delete("/sessions/{session_id}")
async def end_session(
    session_id: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    إنهاء جلسة محددة

    Parameters:
        session_id: معرف الجلسة
        current_user: المستخدم الحالي
        db: جلسة قاعدة البيانات
    """
    session = (
        db.query(models.UserSession)
        .filter(
            models.UserSession.session_id == session_id,
            models.UserSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")

    db.delete(session)
    db.commit()

    log_user_event(db, current_user.id, "session_ended", {"session_id": session_id})
    return {"message": "تم إنهاء الجلسة بنجاح"}


@router.post("/password-strength")
async def check_password_strength(password: str):
    """
    التحقق من قوة كلمة المرور

    Parameters:
        password: كلمة المرور المراد فحصها
    """
    strength = 0
    suggestions = []

    if len(password) >= 8:
        strength += 1
    else:
        suggestions.append("يجب أن تكون كلمة المرور 8 أحرف على الأقل")

    if any(c.isupper() for c in password):
        strength += 1
    else:
        suggestions.append("يجب أن تحتوي على حرف كبير واحد على الأقل")

    if any(c.islower() for c in password):
        strength += 1
    else:
        suggestions.append("يجب أن تحتوي على حرف صغير واحد على الأقل")

    if any(c.isdigit() for c in password):
        strength += 1
    else:
        suggestions.append("يجب أن تحتوي على رقم واحد على الأقل")

    if any(not c.isalnum() for c in password):
        strength += 1
    else:
        suggestions.append("يجب أن تحتوي على رمز خاص واحد على الأقل")

    strength_text = {
        0: "ضعيفة جداً",
        1: "ضعيفة",
        2: "متوسطة",
        3: "جيدة",
        4: "قوية",
        5: "قوية جداً",
    }

    return {
        "strength": strength,
        "strength_text": strength_text[strength],
        "suggestions": suggestions,
    }


@router.post("/security-questions")
async def set_security_questions(
    questions: schemas.SecurityQuestionsSet,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    تعيين أسئلة الأمان للمستخدم

    Parameters:
        questions: نموذج أسئلة الأمان
        current_user: المستخدم الحالي
        db: جلسة قاعدة البيانات
    """
    # تشفير الإجابات قبل التخزين
    encrypted_answers = {q.question: utils.hash(q.answer) for q in questions.questions}

    current_user.security_questions = encrypted_answers
    db.commit()

    log_user_event(db, current_user.id, "security_questions_set")
    return {"message": "تم تعيين أسئلة الأمان بنجاح"}


@router.post("/verify-security-questions")
async def verify_security_questions(
    answers: List[schemas.SecurityQuestionAnswer],
    email: EmailStr,
    db: Session = Depends(database.get_db),
):
    """
    التحقق من إجابات أسئلة الأمان

    Parameters:
        answers: قائمة الإجابات
        email: البريد الإلكتروني للمستخدم
        db: جلسة قاعدة البيانات
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not user.security_questions:
        raise HTTPException(
            status_code=404, detail="المستخدم غير موجود أو لم يتم تعيين أسئلة الأمان"
        )

    correct_answers = 0
    for answer in answers:
        stored_answer = user.security_questions.get(answer.question)
        if stored_answer and utils.verify(answer.answer, stored_answer):
            correct_answers += 1

    if correct_answers < len(answers):
        raise HTTPException(status_code=400, detail="بعض الإجابات غير صحيحة")

    # إنشاء رمز إعادة تعيين كلمة المرور
    token = create_password_reset_token(email)
    user.reset_token = token
    user.reset_token_expires = datetime.now() + TOKEN_EXPIRY
    db.commit()

    return {"reset_token": token}


def create_verification_token(email: str) -> str:
    """
    إنشاء رمز التحقق من البريد الإلكتروني

    Parameters:
        email: البريد الإلكتروني

    Returns:
        str: رمز التحقق
    """
    expire = datetime.utcnow() + timedelta(days=1)
    to_encode = {"exp": expire, "sub": email}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
