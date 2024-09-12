from jose import JWTError, jwt
from datetime import datetime, timedelta
from . import schemas, database, models
from sqlalchemy.orm import Session
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from .config import settings
import logging

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# إعداد البيانات المطلوبة لتشفير وفك تشفير JWT باستخدام RS256
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


# قراءة المفتاح العام من الملف
def read_public_key():
    try:
        with open(settings.rsa_public_key_path, "rb") as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error reading public key: {str(e)}")
        raise


# قراءة المفتاح الخاص من الملف
def read_private_key():
    try:
        with open(settings.rsa_private_key_path, "rb") as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error reading private key: {str(e)}")
        raise


# إنشاء رمز JWT
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    try:
        private_key = read_private_key()
        encoded_jwt = jwt.encode(to_encode, private_key, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise


# التحقق من صحة الرمز JWT
def verify_access_token(token: str, credentials_exception):
    try:
        public_key = read_public_key()
        logger.info(f"Public Key (first 50 chars): {public_key[:50]}...")
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[ALGORITHM],
            options={"verify_signature": True},
        )
        logger.info(f"Decoded Payload: {payload}")

        id: str = payload.get("user_id")
        if id is None:
            logger.warning("User ID not found in token payload")
            raise credentials_exception
        token_data = schemas.TokenData(id=id)
        return token_data
    except JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in verify_access_token: {str(e)}")
        raise credentials_exception


# الحصول على المستخدم الحالي بناءً على رمز JWT
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_data = verify_access_token(token, credentials_exception)
        user = db.query(models.User).filter(models.User.id == token_data.id).first()
        if user is None:
            logger.warning(f"User not found for id: {token_data.id}")
            raise credentials_exception
        return user
    except Exception as e:
        logger.error(f"Error in get_current_user: {str(e)}")
        raise credentials_exception
