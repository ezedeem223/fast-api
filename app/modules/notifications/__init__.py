"""Notifications domain package."""

from .realtime import ConnectionManager, manager

__all__ = [
    "ConnectionManager",
    "manager",
]
