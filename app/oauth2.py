from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from . import schemas, database, models
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def read_key_file(file_path: str) -> str:
    try:
        with open(file_path, "r") as key_file:
            key_data = key_file.read().strip()
            if not key_data:
                raise ValueError(f"Key file is empty: {file_path}")
            return key_data
    except Exception as e:
        raise ValueError(f"Error reading key file: {file_path}, error: {str(e)}")


# تحميل المفاتيح
PRIVATE_KEY = settings._rsa_private_key
PUBLIC_KEY = settings._rsa_public_key

ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    # استخدم المفتاح الخاص لتوقيع التوكن
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def verify_access_token(token: str, credentials_exception):
    try:
        # استخدم المفتاح العام للتحقق من التوكن
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])

        id: str = str(payload.get("user_id"))
        if id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=id)
    except JWTError:
        raise credentials_exception

    return token_data


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_access_token(token, credentials_exception)

    user = db.query(models.User).filter(models.User.id == token_data.id).first()
    if user is None:
        raise credentials_exception
    return user
