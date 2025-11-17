"""Core configuration package."""

from .settings import CustomConnectionConfig, Settings
from .environment import get_settings, get_mail_client

settings = get_settings()
fm = get_mail_client()

__all__ = ["CustomConnectionConfig", "Settings", "settings", "fm", "get_settings"]
