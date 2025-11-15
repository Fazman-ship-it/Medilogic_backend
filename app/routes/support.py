
from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user, require_role
from typing import List
from app.schemas import SupportTicketCreate
from uuid import UUID
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/support", tags=["Support"])

@router.post("/tickets", response_model=schemas.SupportTicketResponse)
def create_ticket(
    ticket: schemas.SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Create the ticket with organization_id attached
    new_ticket = models.SupportTicket(
        user_id=current_user.id,
        subject=ticket.subject,
        status="open",
        organization_id=current_user.organization_id
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    # 2. Add the initial message
    initial_message = models.SupportMessage(
        ticket_id=new_ticket.id,
        sender_id=current_user.id,
        message=ticket.message
    )
    db.add(initial_message)
    db.commit()
    db.refresh(initial_message)

    # 3. Manually attach messages for response
    new_ticket.messages = [initial_message]
    new_ticket.replies = []

    # 4. Reload ticket with full nested info for consistent response
    ticket_with_info = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),                                   # ticket creator
        joinedload(models.SupportTicket.organization),                           # organization info
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)  # message sender
    ).filter(models.SupportTicket.id == new_ticket.id).first()

    return ticket_with_info

@router.get("/tickets", response_model=schemas.PaginatedSupportTickets)
def list_all_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket)

    # Role-based filtering
    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    total = query.count()

    # Minimal update: include messages and message sender info
    tickets = query.options(
        joinedload(models.SupportTicket.user),                                   # ticket creator
        joinedload(models.SupportTicket.organization),                           # organization info
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)  # message sender
    ).order_by(
        models.SupportTicket.created_at.desc()
    ).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": tickets
    }
    

@router.get("/tickets/{ticket_id}", response_model=schemas.SupportTicketResponse)
def get_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # ✅ removed require_role
):
    query = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),                                   # ticket creator
        joinedload(models.SupportTicket.organization),                           # organization info
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)  # message sender
    ).filter(models.SupportTicket.id == ticket_id)

    # Role-based access control
    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))  # only admin tickets
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return ticket


@router.patch("/tickets/{ticket_id}/status", response_model=schemas.SupportTicketResponse)
def update_ticket_status(
    ticket_id: UUID,
    status: schemas.TicketStatus,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # ✅ removed require_role
):
    query = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),                                   # ticket creator
        joinedload(models.SupportTicket.organization),                           # organization info
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)  # message sender
    ).filter(models.SupportTicket.id == ticket_id)

    # Role-based access
    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))  # any admin ticket
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Update status
    ticket.status = status
    db.commit()
    db.refresh(ticket)

    return ticket


from sqlalchemy.orm import joinedload

@router.post("/replies", response_model=schemas.SupportReplyResponse)
def create_reply(
    reply: schemas.SupportReplyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(models.SupportTicket.id == reply.ticket_id)

    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found")

    # Create the reply
    new_reply = models.SupportReply(
        ticket_id=reply.ticket_id,
        admin_id=current_user.id,
        message=reply.message
    )
    db.add(new_reply)
    db.commit()
    db.refresh(new_reply)

    # Reload reply with admin info for response
    reply_with_info = db.query(models.SupportReply).options(
        joinedload(models.SupportReply.admin)  # load admin user info
    ).filter(models.SupportReply.id == new_reply.id).first()

    return reply_with_info


@router.post("/messages", response_model=schemas.SupportMessageResponse)
def post_support_message(
    msg: schemas.SupportMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(models.SupportTicket.id == msg.ticket_id)

    # Role-based access
    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))  # any admin org ticket
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    elif current_user.role in ["driver", "client"]:
        # Clients/Drivers can only reply to their own ticket
        query = query.filter(models.SupportTicket.user_id == current_user.id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Create the message
    message = models.SupportMessage(
        ticket_id=msg.ticket_id,
        sender_id=current_user.id,
        message=msg.message
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # Reload message with sender info for response
    message_with_info = db.query(models.SupportMessage).options(
        joinedload(models.SupportMessage.sender)  # load sender info
    ).filter(models.SupportMessage.id == message.id).first()

    return message_with_info