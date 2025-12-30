"""Compatibility shim for moderation services.

Provides a stable import surface during the migration to `app.modules.moderation`.
"""

from app.modules.moderation.service import (
    ban_user,
    calculate_ban_duration,
    check_auto_ban,
    process_report,
    warn_user,
)

__all__ = [
    "ban_user",
    "calculate_ban_duration",
    "check_auto_ban",
    "process_report",
    "warn_user",
]
