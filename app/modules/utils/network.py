"""Networking helpers (IP management)."""

from __future__ import annotations

import ipaddress
import time
from datetime import datetime, timezone

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app import models
from fastapi import Request

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
            expires_at = ban.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if expires_at and expires_at < now:
                db.delete(ban)
                db.commit()
                return False
            return True
        return False
    except ProgrammingError as pe:  # pragma: no cover - defensive logging
        # Fail open if schema is missing in early migrations; do not block requests.
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


def parse_json_response(response) -> dict | None:
    """Safely parse a JSON response object; returns None on failure and logs it."""
    try:
        return response.json()
    except Exception as exc:
        logger.warning("non_json_response", extra={"error": str(exc)})
        return None


def with_retry(func, retries: int = 3, backoff: float = 0.1):
    """Invoke func with retry/backoff on TimeoutError; re-raises other exceptions."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except TimeoutError as exc:
            last_exc = exc
            logger.warning("network_timeout", extra={"attempt": attempt})
            if attempt < retries:
                time.sleep(backoff)
        except Exception as exc:
            logger.error("network_error", extra={"error": str(exc)})
            raise
    if last_exc:
        raise last_exc


def safe_request(func, retries: int = 3, backoff: float = 0.1):
    """
    Wrapper around with_retry that logs failures and returns None instead of raising
    so callers can degrade gracefully.
    """
    try:
        return with_retry(func, retries=retries, backoff=backoff)
    except Exception as exc:
        logger.error("network_request_failed", extra={"error": str(exc)})
        return None


__all__ = [
    "get_client_ip",
    "is_ip_banned",
    "detect_ip_evasion",
    "parse_json_response",
    "with_retry",
    "safe_request",
]
