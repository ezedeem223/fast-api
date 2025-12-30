"""Support router for ticket creation, responses, and status updates.

Auth required; models map to support tickets/responses stored via services. Minimal
logic here—delegates to services for validations and notifications.
"""

from typing import List

from sqlalchemy.orm import Session

from app.core.database import get_db
from fastapi import APIRouter, Depends, HTTPException

# Import project modules
from .. import models, oauth2, schemas

router = APIRouter(prefix="/support", tags=["Support"])

# ------------------------------------------------------------------
#                         Endpoints
# ------------------------------------------------------------------


@router.post("/tickets", response_model=schemas.Ticket)
async def create_ticket(
    ticket: schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new support ticket.

    - **ticket**: Data required to create a ticket.
    - **current_user**: The authenticated user creating the ticket.

    Returns the created ticket.
    """
    new_ticket = models.SupportTicket(**ticket.dict(), user_id=current_user.id)
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket


@router.get("/tickets", response_model=List[schemas.Ticket])
async def get_user_tickets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve all support tickets created by the current user.

    - **current_user**: The authenticated user.

    Returns a list of tickets belonging to the user.
    """
    tickets = (
        db.query(models.SupportTicket)
        .filter(models.SupportTicket.user_id == current_user.id)
        .all()
    )
    return tickets


@router.post("/tickets/{ticket_id}/responses", response_model=schemas.TicketResponse)
async def add_ticket_response(
    ticket_id: int,
    response: schemas.TicketResponse,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Add a response to an existing support ticket.

    - **ticket_id**: The ID of the ticket to respond to.
    - **response**: The response content.
    - **current_user**: The authenticated user adding the response.

    Returns the created ticket response.
    """
    ticket = (
        db.query(models.SupportTicket)
        .filter(models.SupportTicket.id == ticket_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    new_response = models.TicketResponse(
        ticket_id=ticket_id, user_id=current_user.id, content=response.content
    )
    db.add(new_response)
    db.commit()
    db.refresh(new_response)
    return new_response
