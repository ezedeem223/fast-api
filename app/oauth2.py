from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from . import schemas, database, models
from sqlalchemy.orm import Session
from fastapi import Depends, status, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from .config import settings
import logging
from typing import Optional
from .database import get_db
from .models import User

# استيراد دوال إدارة الـ IP من ملف utils بدلاً من ملف ip_utils
from .utils import get_client_ip, is_ip_banned, detect_ip_evasion

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعداد OAuth2 لاسترجاع التوكن
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


# نموذج TokenData لتخزين بيانات التوكن
class TokenData(schemas.BaseModel):
    id: Optional[int] = None


def create_access_token(data: dict):
    """
    إنشاء JWT access token مع تحديد وقت انتهاء الصلاحية.

    - يتم نسخ البيانات المُدخلة.
    - يتم إضافة حقل انتهاء الصلاحية باستخدام الوقت الحالي بتوقيت UTC زائد الدقائق المحددة.
    - إذا كان "user_id" موجوداً، يتم تحويله إلى عدد صحيح.
    - يتم تشفير التوكن باستخدام المفتاح الخاص RSA.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    if "user_id" in to_encode:
        try:
            to_encode["user_id"] = int(to_encode["user_id"])
        except ValueError:
            logger.error(f"Invalid user_id format: {to_encode['user_id']}")
            raise ValueError("Invalid user_id format")

    try:
        encoded_jwt = jwt.encode(
            to_encode, settings.rsa_private_key, algorithm=ALGORITHM
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise


def get_current_session(token: str = Depends(oauth2_scheme)):
    """
    استخراج session_id الحالي من التوكن.

    - يتم فك تشفير التوكن باستخدام المفتاح السري.
    - يُعاد session_id إذا كان موجوداً؛ وإلا يتم رفع HTTPException.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        session_id: str = payload.get("session_id")
        if session_id is None:
            raise credentials_exception
        return session_id
    except JWTError:
        raise credentials_exception


def verify_access_token(token: str, credentials_exception):
    """
    التحقق من صحة JWT access token.

    - يتم فك تشفير التوكن باستخدام المفتاح العام RSA.
    - يتم استرجاع والتحقق من صحة user_id.
    - يُعاد كائن TokenData يحتوي على user_id.
    """
    try:
        logger.debug(f"Token to verify: {token[:20]}...")
        payload = jwt.decode(token, settings.rsa_public_key, algorithms=[ALGORITHM])
        logger.debug(f"Decoded Payload: {payload}")

        user_id = payload.get("user_id")
        if user_id is None:
            logger.warning("User ID not found in token payload")
            raise credentials_exception

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            logger.error(f"Invalid user_id in token payload: {user_id}")
            raise credentials_exception

        token_data = TokenData(id=user_id)
        return token_data
    except JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in verify_access_token: {str(e)}")
        raise credentials_exception


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
    request: Request = None,
):
    """
    استرجاع المستخدم الحالي بناءً على التوكن المقدم.

    - إذا توفرت بيانات الطلب، يتم التحقق من عنوان IP الخاص بالعميل.
    - يتم فك تشفير التوكن باستخدام المفتاح العام RSA.
    - يتم التحقق من عدم وجود التوكن في القائمة السوداء.
    - يتم فحص محاولة التحايل باستخدام عناوين IP مختلفة.
    - يتم التحقق مما إذا كان المستخدم محظوراً.
    - يتم تحديث التوكن الحالي للمستخدم في قاعدة البيانات.
    - يُعاد كائن المستخدم.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if request:
        client_ip = get_client_ip(request)
        if is_ip_banned(db, client_ip):
            raise HTTPException(status_code=403, detail="Your IP address is banned")

    try:
        payload = jwt.decode(
            token, settings.rsa_public_key, algorithms=[settings.algorithm]
        )
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=user_id)
    except JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception

    try:
        user = db.query(models.User).filter(models.User.id == token_data.id).first()
        if user is None:
            raise credentials_exception

        # التحقق من أن التوكن غير مدرج في القائمة السوداء
        blacklisted_token = (
            db.query(models.TokenBlacklist)
            .filter(models.TokenBlacklist.token == token)
            .first()
        )
        if blacklisted_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated",
            )

        if request:
            if detect_ip_evasion(db, user.id, client_ip):
                logger.warning(f"Possible IP evasion detected for user {user.id}")
                # يمكن إضافة منطق إضافي هنا مثل:
                # - إرسال إشعار للمسؤول
                # - حظر المستخدم مؤقتاً
                # - طلب مصادقة إضافية

        # التحقق مما إذا كان المستخدم محظوراً
        if user.current_ban_end and user.current_ban_end > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is banned until {user.current_ban_end}",
            )

        # تحديث التوكن الحالي للمستخدم في قاعدة البيانات
        user.current_token = token
        db.commit()

        return user
    except Exception as e:
        logger.error(f"Database Error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    user = get_current_user(token, db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user
