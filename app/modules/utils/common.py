"""Common helpers shared across utility modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app import models

logger = logging.getLogger("app.utils")


def get_user_display_name(user: "models.User") -> str:
    """Provide a user-friendly display name for notifications and logs."""
    return (
        getattr(user, "username", None)
        or getattr(user, "account_username", None)
        or getattr(user, "email", None)
        or user.email
    )


__all__ = ["logger", "get_user_display_name"]
