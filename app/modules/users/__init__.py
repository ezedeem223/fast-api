"""User domain package exports."""

from .associations import post_mentions, user_hashtag_follows
from .models import (
    Badge,
    PrivacyLevel,
    TokenBlacklist,
    User,
    UserActivity,
    UserBadge,
    UserEvent,
    UserIdentity,
    UserRole,
    UserSession,
    UserStatistics,
    UserType,
    VerificationStatus,
)

__all__ = [
    "post_mentions",
    "user_hashtag_follows",
    "UserType",
    "VerificationStatus",
    "PrivacyLevel",
    "UserRole",
    "User",
    "TokenBlacklist",
    "UserActivity",
    "UserEvent",
    "UserSession",
    "UserStatistics",
    "Badge",
    "UserBadge",
    "UserIdentity",
]


def __getattr__(name: str):
    """Helper for   getattr  ."""
    if name == "UserService":
        from app.services.users.service import UserService as _UserService

        return _UserService
    raise AttributeError(f"module 'app.modules.users' has no attribute {name!r}")
