"""Security and authentication utilities."""

from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable

from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from passlib.context import CryptContext

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


def admin_required(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator to ensure that the current user has admin privileges."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        from app.oauth2 import get_current_user  # Lazy import to avoid circular deps

        current_user = await get_current_user()
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return await func(*args, **kwargs)

    return wrapper


def handle_exceptions(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator for handling exceptions and returning a standardized error message."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Unhandled exception in utility function: %s", func.__name__)
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
    "admin_required",
    "handle_exceptions",
    "pwd_context",
]
