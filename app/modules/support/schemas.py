"""Pydantic schemas for support tickets."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from app.modules.users.schemas import UserOut
from app.modules.support.models import TicketStatus


class TicketResponse(BaseModel):
    """Pydantic schema for TicketResponse."""
    id: int
    content: str
    created_at: datetime
    user: UserOut

    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    """Pydantic schema for TicketCreate."""
    subject: str
    description: str


class Ticket(BaseModel):
    """Pydantic schema for Ticket."""
    id: int
    subject: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    responses: List[TicketResponse]

    model_config = ConfigDict(from_attributes=True)


class TicketStatusUpdate(BaseModel):
    """Pydantic schema for TicketStatusUpdate."""
    status: TicketStatus


__all__ = ["Ticket", "TicketCreate", "TicketResponse", "TicketStatusUpdate"]
