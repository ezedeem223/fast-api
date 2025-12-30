"""Compatibility shim that re-exports the canonical user service."""

from app.services.users.service import UserService

__all__ = ["UserService"]
