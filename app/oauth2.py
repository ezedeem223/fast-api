from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from . import schemas, database, models
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from hvac import Client

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Initialize Vault client
vault_client = Client(url="http://127.0.0.1:8200", token=settings.vault_token)
secrets = (
    vault_client.secrets.kv.v2.read_secret_version(path="fastapi")
    .get("data")
    .get("data")
)

# Read private and public keys from Vault
PRIVATE_KEY = secrets["PRIVATE_KEY"]
PUBLIC_KEY = secrets["PUBLIC_KEY"]

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
        detail=f"Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = verify_access_token(token, credentials_exception)

    user = db.query(models.User).filter(models.User.id == token.id).first()
    return user
