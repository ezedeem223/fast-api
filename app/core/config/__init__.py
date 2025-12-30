"""Core configuration package.

Exposes cached `settings` and `FastMail` client so imports are cheap and deterministic.
"""

from .environment import get_mail_client, get_settings
from .settings import CustomConnectionConfig, Settings

settings = get_settings()
fm = get_mail_client()

__all__ = ["CustomConnectionConfig", "Settings", "settings", "fm", "get_settings"]
