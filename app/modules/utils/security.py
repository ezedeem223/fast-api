"""Security and authentication utilities."""

from __future__ import annotations

import base64
import hashlib
from functools import wraps
from typing import Any, Awaitable, Callable

from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from fastapi import HTTPException, status

from app.core.config import settings

from .common import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash(password: str) -> str:
    """Encrypt the password using bcrypt."""
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hashed version."""
    return pwd_context.verify(plain_password, hashed_password)


def generate_encryption_key() -> str:
    """Generate a new symmetric encryption key."""
    return Fernet.generate_key().decode()


def update_encryption_key(old_key: str) -> str:
    """Generate a fresh key (placeholder for re-encryption strategy)."""
    new_key = Fernet.generate_key()
    # Placeholder: applications can add re-encryption logic with old_key/new_key if required.
    _ = Fernet(old_key.encode())
    _ = Fernet(new_key)
    return new_key.decode()


def _normalize_fernet_key(raw_key: str) -> bytes:
    """Return a valid Fernet key from a raw secret, deriving if needed."""
    if not raw_key:
        raise ValueError("Encryption key is not configured")
    raw_bytes = raw_key.encode()
    try:
        Fernet(raw_bytes)
        return raw_bytes
    except Exception:
        digest = hashlib.sha256(raw_bytes).digest()
        return base64.urlsafe_b64encode(digest)


def _get_otp_fernet() -> Fernet:
    """Build a Fernet instance for OTP encryption/decryption."""
    raw_key = settings.otp_encryption_key or settings.secret_key
    key = _normalize_fernet_key(raw_key or "")
    return Fernet(key)


def encrypt_otp_secret(value: str | None) -> str | None:
    """Encrypt OTP secret before persisting to the database."""
    if value is None:
        return None
    fernet = _get_otp_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt_otp_secret(value: str | None) -> str | None:
    """Decrypt OTP secret from the database, falling back for legacy plaintext."""
    if value is None:
        return None
    fernet = _get_otp_fernet()
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        logger.warning("OTP secret is not encrypted; returning plaintext value")
        return value


def password_strength_report(password: str) -> dict:
    """Return a strength score and suggestions for a password."""
    strength = 0
    suggestions: list[str] = []
    if len(password) >= 8:
        strength += 1
    else:
        suggestions.append("Password must be at least 8 characters")
    if any(c.isupper() for c in password):
        strength += 1
    else:
        suggestions.append("Must contain at least one uppercase letter")
    if any(c.islower() for c in password):
        strength += 1
    else:
        suggestions.append("Must contain at least one lowercase letter")
    if any(c.isdigit() for c in password):
        strength += 1
    else:
        suggestions.append("Must contain at least one digit")
    if any(not c.isalnum() for c in password):
        strength += 1
    else:
        suggestions.append("Must contain at least one special character")
    strength_text = {
        0: "Very weak",
        1: "Weak",
        2: "Medium",
        3: "Good",
        4: "Strong",
        5: "Very strong",
    }
    return {
        "strength": strength,
        "strength_text": strength_text[strength],
        "suggestions": suggestions,
    }


def enforce_password_strength(password: str) -> None:
    """Raise HTTPException when a password does not meet minimum strength."""
    if not settings.password_strength_required:
        return
    report = password_strength_report(password)
    if report["strength"] < settings.password_strength_min_score:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Password is too weak",
                "strength": report["strength_text"],
                "suggestions": report["suggestions"],
            },
        )


def admin_required(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Decorator to ensure that the current user has admin privileges."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        from app.oauth2 import get_current_user  # Lazy import to avoid circular deps

        current_user = await get_current_user()
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return await func(*args, **kwargs)

    return wrapper


def handle_exceptions(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Decorator for handling exceptions and returning a standardized error message."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception(
                "Unhandled exception in utility function: %s", func.__name__
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred: {str(exc)}",
            )

    return wrapper


__all__ = [
    "hash",
    "verify",
    "generate_encryption_key",
    "update_encryption_key",
    "encrypt_otp_secret",
    "decrypt_otp_secret",
    "password_strength_report",
    "enforce_password_strength",
    "admin_required",
    "handle_exceptions",
    "pwd_context",
]
