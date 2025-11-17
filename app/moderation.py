"""Compatibility shim for moderation services."""

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
