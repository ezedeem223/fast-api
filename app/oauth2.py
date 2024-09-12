from jose import JWTError, jwt
from datetime import datetime, timedelta
from . import schemas, database, models
from sqlalchemy.orm import Session
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# إعداد البيانات المطلوبة لتشفير وفك تشفير JWT باستخدام RS256
SECRET_KEY = settings.rsa_public_key  # استخدم المفتاح العام لفك التشفير
ALGORITHM = settings.algorithm  # تأكد من أن الخوارزمية هي RS256
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


# إنشاء رمز JWT
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    # توقيع الرمز باستخدام المفتاح الخاص
    encoded_jwt = jwt.encode(to_encode, settings.rsa_private_key, algorithm=ALGORITHM)
    return encoded_jwt


# التحقق من صحة الرمز JWT
def verify_access_token(token: str, credentials_exception):
    try:
        # فك التشفير باستخدام المفتاح العام
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id: str = payload.get("user_id")

        if id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=id)
    except JWTError:
        raise credentials_exception

    return token_data


# الحصول على المستخدم الحالي بناءً على رمز JWT
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = verify_access_token(token, credentials_exception)
    user = db.query(models.User).filter(models.User.id == token.id).first()

    return user
