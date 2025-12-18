"""Link preview helpers."""

from __future__ import annotations

import re
from sqlalchemy.orm import Session

from app import models
from app.link_preview import extract_link_preview


def extract_links(text: str) -> list[str]:
    """Extract http/https links from text; ignore unsupported protocols."""
    if not text:
        return []
    candidates = re.findall(r"(https?://[^\s]+)", text)
    return [url for url in candidates if url.startswith(("http://", "https://"))]


def update_link_preview(db: Session, message_id: int, url: str):
    """
    Update the link preview for a message in the database.

    Uses the external `extract_link_preview` helper.
    """
    link_preview = extract_link_preview(url)
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()


__all__ = ["update_link_preview", "extract_links"]
