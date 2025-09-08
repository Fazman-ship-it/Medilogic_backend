
    # app/routes/chatbot.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import  Tuple,Optional, List
from datetime import datetime

from app import models
from app.schemas import ChatRequest, ChatResponse
from app.dependencies import get_db, get_current_user, require_role
from app.utilites.logging import log_activity

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


def role_help_menu(role: str) -> Tuple[str, List[str]]:
    """Return a role-specific help string and options list."""
    if role == "driver":
        text = "Here’s what I can help you with (Driver):"
        options = [
            "show my trips",
            "urgent trips",
            "trip <id>",
            "next pickup",
            "upload POD <trip_id>",
            "show my incidents",
            "contact support"
        ]
        return text, options
    if role == "client":
        text = "Here’s what I can help you with (Client):"
        options = [
            "show my trips",
            "urgent trips",
            "trip <id>",
            "show my invoices",
            "download invoice <id>",
            "check POD <trip_id>",
            "show my incidents",
            "contact support"
        ]
        return text, options
    if role == "admin":
        text = "Here’s what I can help you with (Admin):"
        options = [
            "show all org trips",
            "urgent trips",
            "trip <id>",
            "invite driver",
            "invite client",
            "show my invite code",
            "show all invoices",
            "show all PODs",
            "show incidents",
            "org compliance",
            "contact support"
        ]
        return text, options
    # super_admin or other
    text = "Here’s what I can help you with (Super Admin):"
    options = [
        "list all organizations",
        "regenerate invite code",
        "view org compli ance",
        "view trips across orgs",
        "contact support"
    ]
    return text, options


@router.post("", response_model=ChatResponse)
def chatbot(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Rule-based chatbot endpoint.
    Accepts: { "message": "text" }
    Returns: { "reply": "text", "options": [...], "data": {...} }
    """
    raw = (body.message or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty message")

    text = raw.lower()

    # --- 1) Greeting / Help (role-based) ---
    if any(k in text for k in ["hi", "hello", "hey"]) and len(text.split()) <= 2:
        reply = f"Hello {current_user.name or 'there'} — how can I help?"
        options = ["help", "trip status", "next pickup", "urgent trips"]
        log_activity(db, current_user.id, "chat_greet", details=f"User greeted chatbot", organization_id=current_user.organization_id)
        return ChatResponse(reply=reply, options=options)

    if "help" in text or "what can you do" in text or "commands" in text:
        help_text, options = role_help_menu(current_user.role)
        reply = f"{help_text}\nYou can try: {', '.join(options)}"
        log_activity(db, current_user.id, "chat_help", details="User requested help", organization_id=current_user.organization_id)
        return ChatResponse(reply=reply, options=options)

    # --- 2) Basic user info intents ---
    if "my name" in text:
        return ChatResponse(reply=f"Your name is {current_user.name}")

    if "my email" in text:
        return ChatResponse(reply=f"Your email is {current_user.email}")

    if "my role" in text:
        return ChatResponse(reply=f"Your role is {current_user.role}")

    if "my org id" in text or "organization id" in text:
        if current_user.organization_id:
            return ChatResponse(reply=f"Your organization ID is {current_user.organization_id}")
        return ChatResponse(reply="You are not currently assigned to an organization.")
    # --- 3) Organization info ---
    org = None
    if current_user.organization_id:
        org = db.query(models.Organization).filter_by(id=current_user.organization_id).first()

    if org and ("organization name" in text or "org name" in text):
        return ChatResponse(reply=f"Organization name: {org.name}")

    if org and ("organization address" in text or "address" in text and "org" in text):
        return ChatResponse(reply=f"Organization address: {org.address_line or 'Not available'}")

    if ("invite code" in text or "invite" in text) and org:
        # Only show invite to admin or super_admin (or change as you like)
        if current_user.role in ["admin", "super_admin"]:
            return ChatResponse(reply=f"Invite code: {org.invite_code}")
        else:
            return ChatResponse(reply="Only organization admins can view the invite code.")

    if ("compliance" in text or "license" in text) and org:
        if current_user.role in ["admin", "super_admin"]:
            return ChatResponse(
                reply=f"License: {org.license_number or 'N/A'}, ICO: {org.ico_registered}, retention: {org.data_retention_years or 'N/A'}"
            )
        return ChatResponse(reply="You must be an admin to view compliance details.")

    # --- 4) Trips management ---
    # Ask for trip ID if user says "trip status"
    if "trip status" in text:
        return ChatResponse(reply="Please provide the Trip ID (UUID) like: trip <uuid>")

    # Provide trip by explicit "trip <uuid>"
    if text.startswith("trip "):
        parts = text.split()
        if len(parts) >= 2:
            maybe_id = parts[1]
            try:
                trip_id = UUID(maybe_id)
                trip = db.query(models.Trip).filter(
                    models.Trip.id == trip_id,
                    models.Trip.organization_id == current_user.organization_id
                ).first()
                if not trip:
                    return ChatResponse(reply=f"No trip found with ID {trip_id}")
                # Send useful structured data too
                data = {
                    "id": str(trip.id),
                    "status": trip.status,
                    "priority": trip.priority,
                    "scheduled_time": trip.scheduled_time.isoformat() if trip.scheduled_time else None,
                    "driver_name": trip.driver_name,
                    "pickup_location": trip.pickup_location,
                    "dropoff_location": trip.dropoff_location
                }
                log_activity(db, current_user.id, "chat_trip_lookup", details=f"Looked up trip {trip_id}", organization_id=current_user.organization_id, trip_id=trip_id)
                return ChatResponse(reply=f"Trip {trip.id} is '{trip.status}' (priority: {trip.priority})", data=data)
            except Exception:
                return ChatResponse(reply="Invalid Trip ID format. Please provide a valid UUID.")
        return ChatResponse(reply="Please provide a Trip ID like: trip <uuid>")

    # Urgent trips (admins)
    if "urgent trips" in text:
        if current_user.role != "admin":
            return ChatResponse(reply="Only admins can list urgent trips for the organization.")
        urgent = db.query(models.Trip).filter(
            models.Trip.priority.ilike("urgent"),
            models.Trip.organization_id == current_user.organization_id,
            models.Trip.is_deleted == False
        ).all()
        summary = f"You have {len(urgent)} urgent trips."
        # optionally provide a small list of IDs
        items = [{"id": str(t.id), "scheduled_time": t.scheduled_time.isoformat() if t.scheduled_time else None} for t in urgent[:10]]
        log_activity(db, current_user.id, "chat_urgent_trips", details=f"Fetched {len(urgent)} urgent trips", organization_id=current_user.organization_id)
        return ChatResponse(reply=summary, data={"items": items})

    # Next pickup (driver/client)
    if "next trip" in text or "next pickup" in text:
        # For drivers you might limit to their assigned trips; for clients it could be org next
        q = db.query(models.Trip).filter(
            models.Trip.organization_id == current_user.organization_id,
            models.Trip.is_deleted == False
        ).order_by(models.Trip.scheduled_time.asc())
        next_trip = q.first()
        if next_trip:
            log_activity(db, current_user.id, "chat_next_trip", details=f"Fetched next trip {next_trip.id}", organization_id=current_user.organization_id, trip_id=next_trip.id)
            return ChatResponse(reply=f"Next trip {next_trip.id} scheduled at {next_trip.scheduled_time}", data={"id": str(next_trip.id)})
        return ChatResponse(reply="No upcoming trips found.")

    # --- 5) Proof of Delivery (POD) ---
    if "proof of delivery" in text or text.startswith("pod") or "pod" in text:
        pod = db.query(models.POD).filter_by(organization_id=current_user.organization_id).order_by(models.POD.created_at.desc()).first()
        if pod:
            log_activity(db, current_user.id, "chat_pod_lookup", details=f"Fetched latest POD {pod.id}", organization_id=current_user.organization_id)
            return ChatResponse(reply=f"Latest POD at {pod.created_at}", data={"attachment_url": pod.attachment_url, "created_at": pod.created_at.isoformat()})
        return ChatResponse(reply="No proof of delivery found for your organization.")

    # --- 6) Incidents (list/open/report) ---
    if "incident" in text:
        # "show incidents" or "open incidents"
        if "open incidents" in text or "unresolved" in text:
            incidents = db.query(models.Incident).filter(
                models.Incident.organization_id == current_user.organization_id,
                models.Incident.status != "resolved"
            ).all()
            return ChatResponse(reply=f"You have {len(incidents)} open incidents.", data={"items": [{"id": str(i.id), "status": i.status} for i in incidents]})
        # show all incidents
        if "show incidents" in text or "my incidents" in text:
            incidents = db.query(models.Incident).filter_by(organization_id=current_user.organization_id).all()
            return ChatResponse(reply=f"You have {len(incidents)} incidents on record.", data={"items": [{"id": str(i.id), "status": i.status} for i in incidents]})
        # incident <id>
        if text.startswith("incident "):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    inc_id = UUID(parts[1])
                    inc = db.query(models.Incident).filter_by(id=inc_id, organization_id=current_user.organization_id).first()
                    if not inc:
                        return ChatResponse(reply="Incident not found.")
                    log_activity(db, current_user.id, "chat_incident_lookup", details=f"Looked up incident {inc_id}", organization_id=current_user.organization_id)
                    return ChatResponse(reply=f"Incident {inc.id} - {inc.description} - status: {inc.status}", data={"id": str(inc.id), "status": inc.status, "description": inc.description})
                except Exception:
                    return ChatResponse(reply="Invalid Incident ID. Provide a UUID.")
        # If user says "report incident" - give instructions (you can extend to create)
        if "report incident" in text or "open incident" in text:
            return ChatResponse(reply="To report an incident, please use the 'Report Incident' form in the dashboard or call support. Provide description, location, and photos if available.")

    # --- 7) Invoices ---
    if "invoice" in text:
        if "show" in text or "my invoices" in text or "list invoices" in text:
            invoices = db.query(models.Invoice).filter_by(organization_id=current_user.organization_id).order_by(models.Invoice.created_at.desc()).limit(25).all()
            return ChatResponse(reply=f"You have {len(invoices)} invoices.", data={"items": [{"id": str(inv.id), "amount": inv.amount, "status": inv.status} for inv in invoices]})
        if text.startswith("invoice "):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    inv_id = UUID(parts[1])
                    inv = db.query(models.Invoice).filter_by(id=inv_id, organization_id=current_user.organization_id).first()
                    if not inv:
                        return ChatResponse(reply="Invoice not found.")
                    log_activity(db, current_user.id, "chat_invoice_lookup", details=f"Looked up invoice {inv_id}", organization_id=current_user.organization_id)
                    return ChatResponse(reply=f"Invoice {inv.id} - Amount: {inv.amount} - Status: {inv.status}", data={"id": str(inv.id), "amount": inv.amount, "status": inv.status, "pdf_url": getattr(inv, "pdf_url", None)})
                except Exception:
                    return ChatResponse(reply="Invalid Invoice ID. Provide a UUID.")

    # --- 8) Fallback ---
    log_activity(db, current_user.id, "chat_fallback", details=f"Unrecognized chat message: {raw}", organization_id=current_user.organization_id)
    return ChatResponse(reply="Sorry, I didn't understand that. Try 'help' to see what I can do.")