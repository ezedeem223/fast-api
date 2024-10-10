from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List

router = APIRouter(prefix="/support", tags=["Support"])


@router.post("/tickets", response_model=schemas.Ticket)
async def create_ticket(
    ticket: schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
