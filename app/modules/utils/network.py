"""Networking helpers (IP management)."""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app import models
from .common import logger


def get_client_ip(request: Request) -> str:
    """Retrieve the client's IP address from headers or connection info."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def is_ip_banned(db: Session, ip_address: str) -> bool:
    """Check if the IP address is currently banned, clearing expired bans."""
    try:
        ban = (
            db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
        )
        if ban:
            if ban.expires_at and ban.expires_at < datetime.now():
                db.delete(ban)
                db.commit()
                return False
            return True
        return False
    except ProgrammingError as pe:  # pragma: no cover - defensive logging
        logger.error("ProgrammingError checking IP ban for %s: %s", ip_address, pe)
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error checking IP ban for %s: %s", ip_address, exc)
        return False


def detect_ip_evasion(db: Session, user_id: int, current_ip: str) -> bool:
    """Detect if user is potentially evading bans via different IP classes."""
    user_ips = (
        db.query(models.UserSession.ip_address)
        .filter(models.UserSession.user_id == user_id)
        .distinct()
        .all()
    )
    user_ips = [ip[0] for ip in user_ips]
    for ip in user_ips:
        if ip != current_ip and (
            ipaddress.ip_address(ip).is_private
            != ipaddress.ip_address(current_ip).is_private
        ):
            return True
    return False


__all__ = ["get_client_ip", "is_ip_banned", "detect_ip_evasion"]
