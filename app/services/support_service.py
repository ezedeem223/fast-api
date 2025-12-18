"""Support ticket ancillary flows for creation, responses, and moderation."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.modules.support import TicketResponseModel


def _require_user(user):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")
    return user


class SupportService:
    """Minimal helper to create and respond to support tickets with auth checks."""

    def __init__(self, db: Session):
        self.db = db

    def create_ticket(self, *, current_user, subject: str, description: str) -> models.SupportTicket:
        _require_user(current_user)
        if not subject or not description:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing subject/description")
        ticket = models.SupportTicket(user_id=current_user.id, subject=subject, description=description)
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def add_response(self, *, current_user, ticket_id: int, content: str) -> TicketResponseModel:
        _require_user(current_user)
        if not content or not content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content required")
        ticket = self.db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
        resp = TicketResponseModel(ticket_id=ticket_id, user_id=current_user.id, content=content.strip())
        self.db.add(resp)
        self.db.commit()
        self.db.refresh(resp)
        return resp


__all__ = ["SupportService"]
