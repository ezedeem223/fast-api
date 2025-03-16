"""
File: oauth2.py
Description: This module handles JWT token creation, verification, and retrieval of the current user and admin.
It integrates with IP management utilities for enhanced security and performs proper error handling and logging.
"""

# ============================================
# Imports and Dependencies
# ============================================
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
from .models import User, UserRole
from .utils import get_client_ip, is_ip_banned, detect_ip_evasion

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure OAuth2 to retrieve the token from the "login" endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


# ============================================
# Token Data Model
# ============================================
class TokenData(schemas.BaseModel):
    """
    Schema to store token data.
    """

    id: Optional[int] = None


# ============================================
# Token Creation Function
# ============================================
def create_access_token(data: dict):
    """
    Creates a JWT access token with an expiration time.

    - Copies the input data.
    - Adds an expiration field using the current UTC time plus the specified minutes.
    - If 'user_id' is present, converts it to an integer.
    - Encodes the token using the RSA private key.
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


# ============================================
# Current Session Retrieval Function
# ============================================
def get_current_session(token: str = Depends(oauth2_scheme)):
    """
    Extracts the current session_id from the token.

    - Decodes the token using the RSA public key.
    - Returns the session_id if present; otherwise, raises HTTPException.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Credentials",  # Message in English
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Updated to use RSA public key for decoding
        payload = jwt.decode(token, settings.rsa_public_key, algorithms=[ALGORITHM])
        session_id: str = payload.get("session_id")
        if session_id is None:
            raise credentials_exception
        return session_id
    except JWTError:
        raise credentials_exception


# ============================================
# Token Verification Function
# ============================================
def verify_access_token(token: str, credentials_exception):
    """
    Verifies the JWT access token.

    - Decodes the token using the RSA public key.
    - Retrieves and validates the user_id.
    - Returns a TokenData object containing the user_id.
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


# ============================================
# Current User Retrieval Function
# ============================================
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
    request: Request = None,
):
    """
    Retrieves the current user based on the provided token.

    - If the request is provided, checks the client's IP address.
    - Decodes the token using the RSA public key.
    - Verifies that the token is not blacklisted.
    - Checks for IP evasion attempts.
    - Ensures that the user is not banned.
    - Updates the user's current token in the database.
    - Returns the User object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Credentials",  # Message in English
        headers={"WWW-Authenticate": "Bearer"},
    )

    if request:
        client_ip = get_client_ip(request)
        if is_ip_banned(db, client_ip):
            raise HTTPException(status_code=403, detail="Your IP address is banned")

    try:
        payload = jwt.decode(token, settings.rsa_public_key, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise credentials_exception
        token_data = TokenData(id=user_id)
    except JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception

    try:
        user = db.query(models.User).filter(models.User.id == token_data.id).first()
        if user is None:
            raise credentials_exception

        # Check if the token is blacklisted
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
            client_ip = get_client_ip(request)
            if detect_ip_evasion(db, user.id, client_ip):
                logger.warning(f"Possible IP evasion detected for user {user.id}")

        # Check if the user is banned
        if user.current_ban_end and user.current_ban_end > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is banned until {user.current_ban_end}",
            )

        # Update the user's current token in the database
        user.current_token = token
        db.commit()

        return user
    except Exception as e:
        logger.error(f"Database Error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ============================================
# Admin User Retrieval Function
# ============================================
def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """
    Retrieves the current admin user.

    - Retrieves the current user.
    - Checks if the user's role is 'admin'.
    - Raises HTTPException if the user does not have admin privileges.
    """
    user = get_current_user(token, db)
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user
