"""Support ticket ancillary flows for creation, responses, and moderation."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.modules.support import TicketResponseModel
from fastapi import HTTPException, status


def _require_user(user):
    """Helper for  require user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required"
        )
    return user


class SupportService:
    """Minimal helper to create and respond to support tickets with auth checks."""

    def __init__(self, db: Session):
        self.db = db

    def create_ticket(
        self, *, current_user, subject: str, description: str
    ) -> models.SupportTicket:
        _require_user(current_user)
        if not subject or not description:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing subject/description",
            )
        ticket = models.SupportTicket(
            user_id=current_user.id, subject=subject, description=description
        )
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def add_response(
        self, *, current_user, ticket_id: int, content: str
    ) -> TicketResponseModel:
        _require_user(current_user)
        if not content or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Content required"
            )
        ticket = (
            self.db.query(models.SupportTicket)
            .filter(models.SupportTicket.id == ticket_id)
            .first()
        )
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
            )
        # Normalize whitespace to keep responses consistent.
        resp = TicketResponseModel(
            ticket_id=ticket_id, user_id=current_user.id, content=content.strip()
        )
        self.db.add(resp)
        self.db.commit()
        self.db.refresh(resp)
        return resp

    def update_ticket_status(
        self, ticket_id: int, status_value: models.TicketStatus
    ) -> models.SupportTicket:
        ticket = (
            self.db.query(models.SupportTicket)
            .filter(models.SupportTicket.id == ticket_id)
            .first()
        )
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
            )
        ticket.status = status_value
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def submit_report(
        self, reporter_id: int, reason: str, post_id: int | None, comment_id: int | None
    ) -> models.Report:
        report = models.Report(
            reporter_id=reporter_id,
            reason=reason,
            post_id=post_id,
            comment_id=comment_id,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report


__all__ = ["SupportService"]
