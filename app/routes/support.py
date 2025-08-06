
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user, require_role
from typing import List
from app.schemas import SupportTicketCreate
from uuid import UUID

router = APIRouter(prefix="/support", tags=["Support"])

@router.post("/tickets", response_model=schemas.SupportTicketResponse)
def create_ticket(
    ticket: schemas.SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ 1. Create the ticket with organization_id attached
    new_ticket = models.SupportTicket(
        user_id=current_user.id,
        subject=ticket.subject,
        status="open",
        organization_id=current_user.organization_id  # ✅ enforce tenant ownership
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    # ✅ 2. Add the initial message
    initial_message = models.SupportMessage(
        ticket_id=new_ticket.id,
        sender_id=current_user.id,
        message=ticket.message
    )
    db.add(initial_message)
    db.commit()
    db.refresh(initial_message)

    # ✅ 3. Manually attach messages for response
    new_ticket.messages = [initial_message]
    new_ticket.replies = []

    return new_ticket

@router.get("/tickets", response_model=List[schemas.SupportTicketResponse])
def list_all_tickets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ access org
):
    return db.query(models.SupportTicket).filter(
        models.SupportTicket.organization_id == current_user.organization_id
    ).order_by(models.SupportTicket.created_at.desc()).all()

@router.get("/tickets/{ticket_id}", response_model=schemas.SupportTicketResponse)
def get_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ access org
):
    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.organization_id == current_user.organization_id  # ✅ restrict to org
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return ticket

@router.patch("/tickets/{ticket_id}/status", response_model=schemas.SupportTicketResponse)
def update_ticket_status(
    ticket_id: UUID,
    status: schemas.TicketStatus,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ needed to access org
):
    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.organization_id == current_user.organization_id  # ✅ org filter
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = status
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/replies", response_model=schemas.SupportReplyResponse)
def create_reply(
    reply: schemas.SupportReplyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ org access
):
    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == reply.ticket_id,
        models.SupportTicket.organization_id == current_user.organization_id  # ✅ secure!
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found")

    new_reply = models.SupportReply(
        ticket_id=reply.ticket_id,
        admin_id=current_user.id,
        message=reply.message
    )
    db.add(new_reply)
    db.commit()
    db.refresh(new_reply)
    return new_reply


@router.post("/messages", response_model=schemas.SupportMessageResponse)
def post_support_message(
    msg: schemas.SupportMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Admin or Client
):
    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == msg.ticket_id,
        models.SupportTicket.organization_id == current_user.organization_id  # ✅ Tenant safe
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # ✅ If client, ensure they are replying only to their own ticket
    if current_user.role == "client" and ticket.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only reply to your own ticket.")

    message = models.SupportMessage(
        ticket_id=msg.ticket_id,
        sender_id=current_user.id,
        message=msg.message
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message