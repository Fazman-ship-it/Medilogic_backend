
from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user, require_role
from typing import List
from app.schemas import SupportTicketCreate
from uuid import UUID
from sqlalchemy.orm import joinedload
from app.utilites.support_notification import  notify_ticket_users

router = APIRouter(prefix="/support", tags=["Support"])


@router.post("/tickets", response_model=schemas.SupportTicketResponse)
def create_ticket(
    ticket: schemas.SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🔒 Every ticket belongs to an organisation
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User is not attached to an organisation")

    new_ticket = models.SupportTicket(
        user_id=current_user.id,
        subject=ticket.subject,
        status="open",
        organization_id=current_user.organization_id  # ✅ ALWAYS set
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    initial_message = models.SupportMessage(
        ticket_id=new_ticket.id,
        sender_id=current_user.id,
        message=ticket.message
    )
    db.add(initial_message)
    db.commit()
    db.refresh(initial_message)

    notify_ticket_users(db, new_ticket, current_user, initial_message.message)

    ticket_with_info = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),
        joinedload(models.SupportTicket.organization),
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)
    ).filter(models.SupportTicket.id == new_ticket.id).first()

    return ticket_with_info
    
@router.get("/tickets", response_model=schemas.PaginatedSupportTickets)
def list_all_tickets(
    status: str = Query(None),
    organization_id: UUID = Query(None),
    user_name: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(
        models.SupportTicket.is_deleted == False
    )

    # --- Role-based filtering ---
    if current_user.role == "super_admin":
        # ✅ ONLY tickets CREATED BY ADMINS
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

    elif current_user.role == "admin":
        # ✅ ALL tickets in their organisation
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role in ["client", "driver"]:
        # ✅ ONLY tickets THEY created
        query = query.filter(
            models.SupportTicket.user_id == current_user.id
        )

    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # --- Optional filters ---
    if status:
        query = query.filter(models.SupportTicket.status == status)

    if user_name:
        query = query.join(models.User).filter(
            models.User.name.ilike(f"%{user_name}%")
        )

    total = query.count()

    tickets = query.options(
        joinedload(models.SupportTicket.user),
        joinedload(models.SupportTicket.organization),
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)
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
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),
        joinedload(models.SupportTicket.organization),
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)
    ).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.is_deleted == False
    )

    if current_user.role == "super_admin":
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

    elif current_user.role == "admin":
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role in ["client", "driver"]:
        query = query.filter(
            models.SupportTicket.user_id == current_user.id
        )

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
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.user),                                   # ticket creator
        joinedload(models.SupportTicket.organization),                           # organization info
        joinedload(models.SupportTicket.messages).joinedload(models.SupportMessage.sender)
    ).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.is_deleted == False
    )

    # 🔒 Role-based access (FIXED)
    if current_user.role == "admin":
        # ✅ Admin can update ALL tickets in their organisation
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role == "super_admin":
        # ✅ Super admin can update ONLY admin-created tickets
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

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
    query = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == reply.ticket_id
    )

    # 🔧 FIX 1: Correct role-based access
    if current_user.role == "admin":
        # ✅ Admin can reply to ANY ticket in their organisation
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role == "super_admin":
        # ✅ Super admin can ONLY reply to admin-created tickets
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

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

    # --- Notify users about the new reply ---
    notify_ticket_users(db, ticket, current_user, new_reply.message)

    # Reload reply with admin info for response
    reply_with_info = db.query(models.SupportReply).options(
        joinedload(models.SupportReply.admin)
    ).filter(models.SupportReply.id == new_reply.id).first()

    return reply_with_info

@router.post("/messages", response_model=schemas.SupportMessageResponse)
def post_support_message(
    msg: schemas.SupportMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # --- Only CLIENT & DRIVER can create messages ---
    if current_user.role not in ["driver", "client"]:
        raise HTTPException(status_code=403, detail="Only clients and drivers can create messages")

    query = db.query(models.SupportTicket).filter(models.SupportTicket.id == msg.ticket_id)

    # Clients/Drivers can ONLY reply to their own ticket
    query = query.filter(models.SupportTicket.user_id == current_user.id)

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

    # --- Notify users about the new message ---
    notify_ticket_users(db, ticket, current_user, message.message)

    # Reload message with sender info for response
    message_with_info = db.query(models.SupportMessage).options(
        joinedload(models.SupportMessage.sender)  # load sender info
    ).filter(models.SupportMessage.id == message.id).first()

    return message_with_info
    
@router.delete("/tickets/{ticket_id}")
def delete_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id)

    # Role-based access
    if current_user.role == "super_admin":
        query = query.filter(models.SupportTicket.organization_id.isnot(None))
    elif current_user.role == "admin":
        query = query.filter(models.SupportTicket.organization_id == current_user.organization_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Soft delete
    ticket.is_deleted = True
    db.commit()

    return {"detail": "Ticket deleted successfully"}
    
@router.get("/tickets/{ticket_id}/replies", response_model=List[schemas.SupportReplyResponse])
def get_ticket_replies(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.is_deleted == False
    )

    # --- Role-based access (FIXED) ---
    if current_user.role == "admin":
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role == "super_admin":
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Load all replies with admin info
    replies = db.query(models.SupportReply).options(
        joinedload(models.SupportReply.admin)
    ).filter(
        models.SupportReply.ticket_id == ticket_id
    ).all()

    return replies
    
@@router.get("/tickets/{ticket_id}/messages", response_model=List[schemas.SupportMessageResponse])
def get_ticket_messages(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.is_deleted == False
    )

    # --- Role-based access (FIXED) ---
    if current_user.role == "admin":
        query = query.filter(
            models.SupportTicket.organization_id == current_user.organization_id
        )

    elif current_user.role == "super_admin":
        query = query.filter(
            models.SupportTicket.user.has(models.User.role == "admin")
        )

    elif current_user.role in ["client", "driver"]:
        query = query.filter(
            models.SupportTicket.user_id == current_user.id
        )

    else:
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = query.first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Load messages with sender info
    messages = db.query(models.SupportMessage).options(
        joinedload(models.SupportMessage.sender)
    ).filter(
        models.SupportMessage.ticket_id == ticket_id
    ).all()

    return messages
    
@router.patch("/messages/{message_id}", response_model=schemas.SupportMessageResponse)
def update_message(
    message_id: UUID,
    message_text: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    message = db.query(models.SupportMessage).options(
        joinedload(models.SupportMessage.sender)
    ).filter(models.SupportMessage.id == message_id).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Access control
    if current_user.role == "super_admin":
        pass  # can edit any message
    elif current_user.role == "admin":
        if message.sender_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot edit another admin's message")
    elif current_user.role in ["client", "driver"]:
        if message.sender_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot edit another user's message")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    message.message = message_text
    db.commit()
    db.refresh(message)

    return message
    

@router.patch("/replies/{reply_id}", response_model=schemas.SupportReplyResponse)
def update_reply(
    reply_id: UUID,
    data: schemas.SupportReplyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    reply = db.query(models.SupportReply).filter(models.SupportReply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == reply.ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # --- Role-based access rules (Option A) ---
    if current_user.role == "admin":
        # Admin can ONLY edit their own replies
        if reply.admin_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only edit your own replies")

    elif current_user.role == "super_admin":
        # Super admin can edit anything
        pass

    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # --- Apply update ---
    reply.message = data.message
    db.commit()
    db.refresh(reply)

    # Reload with admin info
    reply_with_info = db.query(models.SupportReply).options(
        joinedload(models.SupportReply.admin)
    ).filter(models.SupportReply.id == reply.id).first()

    return reply_with_info
    