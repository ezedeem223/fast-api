"""Support/helpdesk models and enums."""

from __future__ import annotations

import enum

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default


class TicketStatus(str, enum.Enum):
    """Enumeration for TicketStatus."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SupportTicket(Base):
    """Top-level support ticket submitted by a user."""

    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        SAEnum(TicketStatus, name="ticket_status_enum"),
        default=TicketStatus.OPEN,
    )
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())
    updated_at = Column(DateTime(timezone=True), onupdate=timestamp_default())

    user = relationship("User", back_populates="support_tickets")
    responses = relationship(
        "TicketResponse", back_populates="ticket", cascade="all, delete-orphan"
    )


class TicketResponse(Base):
    """Staff/user responses attached to a ticket."""

    __tablename__ = "ticket_responses"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    ticket = relationship("SupportTicket", back_populates="responses")
    user = relationship("User")


__all__ = ["TicketStatus", "SupportTicket", "TicketResponse"]
