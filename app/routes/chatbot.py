
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
from app.utilites.shortid import ShortIDMixin

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
    elif role == "client":
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
    elif role == "admin":
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
    else:  # super_admin or other
        text = "Here’s what I can help you with (Super Admin):"
        options = [
            "list all organizations",
            "regenerate invite code",
            "view org compliance",
            "view trips across orgs",
            "contact support"
        ]
    return text, options


def find_by_uuid_or_short_id(queryset, identifier, short_id_attr="short_id"):
    """
    Helper to find a model instance by UUID or short_id.
    queryset: SQLAlchemy query.all() result
    identifier: str
    short_id_attr: attribute name for short_id (default 'short_id')
    """
    try:
        # Try UUID first
        obj_id = UUID(identifier)
        return next((obj for obj in queryset if obj.id == obj_id), None)
    except ValueError:
        # Not a UUID, fallback to short_id
        return next((obj for obj in queryset if getattr(obj, short_id_attr) == identifier), None)


@router.post("", response_model=ChatResponse)
def chatbot(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    raw = (body.message or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty message")

    text = raw.lower()

    # --- 1) Greeting / Help (role-based) ---
    if any(k in text for k in ["hi", "hello", "hey"]) and len(text.split()) <= 2:
        reply = f"Hello {current_user.name or 'there'} — how can I help?"
        options = ["help", "trip status", "next pickup", "urgent trips"]
        log_activity(db, current_user.id, "chat_greet", details="User greeted chatbot")
        return ChatResponse(reply=reply, options=options)

    if "help" in text or "what can you do" in text or "commands" in text:
        help_text, options = role_help_menu(current_user.role)
        reply = f"{help_text}\nYou can try: {', '.join(options)}"
        log_activity(db, current_user.id, "chat_help", details="User requested help")
        return ChatResponse(reply=reply, options=options)

    # --- 2) Basic user info ---
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
        if current_user.role in ["admin", "super_admin"]:
            return ChatResponse(reply=f"Invite code: {org.invite_code}")
        return ChatResponse(reply="Only organization admins can view the invite code.")
    if ("compliance" in text or "license" in text) and org:
        if current_user.role in ["admin", "super_admin"]:
            return ChatResponse(
                reply=f"License: {org.license_number or 'N/A'}, ICO: {org.ico_registered}, retention: {org.data_retention_years or 'N/A'}"
            )
        return ChatResponse(reply="You must be an admin to view compliance details.")

    # --- 4) Trips management ---
    if "trip status" in text:
        return ChatResponse(reply="Please provide the Trip ID (UUID or short_id) like: trip <id>")

    if text.startswith("trip "):
        parts = text.split()
        if len(parts) >= 2:
            identifier = parts[1]
            trips = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id).all()
            trip = find_by_uuid_or_short_id(trips, identifier)
            if not trip:
                return ChatResponse(reply=f"No trip found with ID {identifier}")
            data = {
                "id": str(trip.id),
                "short_id": trip.short_id,
                "status": trip.status,
                "priority": trip.priority,
                "scheduled_time": trip.scheduled_time.isoformat() if trip.scheduled_time else None,
                "driver_name": trip.driver_name,
                "pickup_location": trip.pickup_location,
                "dropoff_location": trip.dropoff_location
            }
            log_activity(db, current_user.id, "chat_trip_lookup", details=f"Looked up trip {identifier}", trip_id=trip.id)
            return ChatResponse(reply=f"Trip {trip.short_id} is '{trip.status}' (priority: {trip.priority})", data=data)
        return ChatResponse(reply="Please provide a Trip ID like: trip <id>")

    if "urgent trips" in text:
        if current_user.role != "admin":
            return ChatResponse(reply="Only admins can list urgent trips for the organization.")
        urgent = db.query(models.Trip).filter(
            models.Trip.priority.ilike("urgent"),
            models.Trip.organization_id == current_user.organization_id,
            models.Trip.is_deleted == False
        ).all()
        summary = f"You have {len(urgent)} urgent trips."
        items = [{"id": str(t.id), "short_id": t.short_id, "scheduled_time": t.scheduled_time.isoformat() if t.scheduled_time else None} for t in urgent[:10]]
        log_activity(db, current_user.id, "chat_urgent_trips", details=f"Fetched {len(urgent)} urgent trips")
        return ChatResponse(reply=summary, data={"items": items})

    if "next trip" in text or "next pickup" in text:
        q = db.query(models.Trip).filter(
            models.Trip.organization_id == current_user.organization_id,
            models.Trip.is_deleted == False
        ).order_by(models.Trip.scheduled_time.asc())
        next_trip = q.first()
        if next_trip:
            log_activity(db, current_user.id, "chat_next_trip", details=f"Fetched next trip {next_trip.id}", trip_id=next_trip.id)
            return ChatResponse(reply=f"Next trip {next_trip.short_id} scheduled at {next_trip.scheduled_time}", data={"id": str(next_trip.id), "short_id": next_trip.short_id})
        return ChatResponse(reply="No upcoming trips found.")

    # --- 5) POD ---
    if "proof of delivery" in text or text.startswith("pod") or "pod" in text:
        pod = db.query(models.POD).filter_by(organization_id=current_user.organization_id).order_by(models.POD.created_at.desc()).first()
        if pod:
            safe_files = []
            try:
                if pod.files:
                    for f in pod.files:
                        safe_files.append({
                            "id": str(getattr(f, "id", "")) if getattr(f, "id", None) else None,
                            "file_url": getattr(f, "file_url", None),
                            "file_type": getattr(f, "file_type", None),
                            "filename": getattr(f, "filename", None),
                            "created_ at" : getattr(f, "created_at", None). isoformat() if getattr(f, "created_at", None) else None,
                        })
            except Exception:
                safe_files = []
                log_activity(db, current_user.id, "chat_pod_lookup", details=f"Fetched latest POD {pod.id}")
            return ChatResponse(
                reply=f"Latest POD {pod.short_id} for trip {pod.trip_id} created at {pod.created_at}",
                data={
                    "files": safe_files,
                    "id": str(pod.id),
                    "created_at": pod.created_at.isoformat() if pod.created_at else None,
                }
            )
        return ChatResponse(reply="No Proof of Delivery records found for your organization.")

    # --- 6) Incidents ---
    if "incident" in text:
        if "open incidents" in text or "unresolved" in text:
            incidents = db.query(models.Incident).filter(
                models.Incident.organization_id == current_user.organization_id,
                models.Incident.status != "resolved"
            ).all()
            return ChatResponse(reply=f"You have {len(incidents)} open incidents.", data={"items": [{"id": str(i.id), "status": i.status, "short_id": i.short_id} for i in incidents]})
        if "show incidents" in text or "my incidents" in text:
            incidents = db.query(models.Incident).filter_by(organization_id=current_user.organization_id).all()
            return ChatResponse(reply=f"You have {len(incidents)} incidents on record.", data={"items": [{"id": str(i.id), "status": i.status, "short_id": i.short_id} for i in incidents]})
        if text.startswith("incident "):
            parts = text.split()
            if len(parts) >= 2:
                identifier = parts[1]
                incidents = db.query(models.Incident).filter(models.Incident.organization_id == current_user.organization_id).all()
                inc = find_by_uuid_or_short_id(incidents, identifier)
                if not inc:
                    return ChatResponse(reply="Incident not found.")
                log_activity(db, current_user.id, "chat_incident_lookup", details=f"Looked up incident {identifier}")
                return ChatResponse(reply=f"Incident {inc.short_id} - {inc.description} - status: {inc.status}", data={"id": str(inc.id), "short_id": inc.short_id, "status": inc.status, "description": inc.description})
        if "report incident" in text or "open incident" in text:
            return ChatResponse(reply="To report an incident, please use the 'Report Incident' form in the dashboard or call support. Provide description, location, and photos if available.")

    # --- 7) Invoices ---
    if "invoice" in text:
        if "show" in text or "my invoices" in text or "list invoices" in text:
            invoices = db.query(models.Invoice).filter_by(organization_id=current_user.organization_id).order_by(models.Invoice.generated_at.desc()).limit(25).all()
            return ChatResponse(reply=f"You have {len(invoices)} invoices.", data={"items": [{"id": str(inv.id), "short_id": inv.short_id, "amount": inv.amount, "status": inv.status} for inv in invoices]})
        if text.startswith("invoice "):
            parts = text.split()
            if len(parts) >= 2:
                identifier = parts[1]
                invoices = db.query(models.Invoice).filter(models.Invoice.organization_id == current_user.organization_id).all()
                inv = find_by_uuid_or_short_id(invoices, identifier)
                if not inv:
                    return ChatResponse(reply="Invoice not found.")
                log_activity(db, current_user.id, "chat_invoice_lookup", details=f"Looked up invoice {identifier}")
                return ChatResponse(
                    reply=f"Invoice {inv.short_id} - Amount: {inv.amount} - Status: {inv.status}",
                    data={"id": str(inv.id), "short_id": inv.short_id, "amount": inv.amount, "status": inv.status, "pdf_url": getattr(inv, "pdf_url", None)}
                )

    # --- 8) Delivery Confirmations (internal + external) ---
    if "delivery confirmation" in text or text.startswith("delivery ") or "delivery status" in text:
        parts = text.split()
        if len(parts) >= 2:
            identifier = parts[1]
            confirmations = db.query(models.DeliveryConfirmation).filter(
                models.DeliveryConfirmation.organization_id == current_user.organization_id
            ).all()
            confirmation = find_by_uuid_or_short_id(confirmations, identifier)
            if confirmation:
                log_activity(
                    db, current_user.id, "chat_delivery_confirmation_lookup",
                    details=f"Looked up delivery confirmation {identifier}",
                    trip_id=confirmation.trip_id
                )
                data = {
                    "id": str(confirmation.id),
                    "short_id": confirmation.short_id,
                    "trip_id": str(confirmation.trip_id),
                    "confirmed_at": confirmation.confirmed_at.isoformat() if confirmation.confirmed_at else None,
                    "pickup_at": confirmation.pickup_at.isoformat() if confirmation.pickup_at else None,
                    "dropoff_at": confirmation.dropoff_at.isoformat() if confirmation.dropoff_at else None,
                    "external_client_name": confirmation.external_client_name,
                    "external_client_email": confirmation.external_client_email,
                    "external_client_signature": confirmation.external_client_signature_path,
                    "pdf_receipt_path": confirmation.pdf_receipt_path,
                    "attachments": confirmation.attachments,
                    "extra_notes": confirmation.extra_notes,
                    "disposal_facility_name": confirmation.disposal_facility_name,
                    "disposal_facility_address": confirmation.disposal_facility_address,
                    "disposal_facility_signature": confirmation.disposal_facility_signature_path,
                    "pickup_photo_path": confirmation.pickup_photo_path,
                    "dropoff_photo_path": confirmation.dropoff_photo_path,
                    "latitude": confirmation.latitude,
                    "longitude": confirmation.longitude,
                }
                return ChatResponse(
                    reply=f"Delivery {confirmation.short_id} for trip {confirmation.trip_id} is confirmed at {confirmation.confirmed_at}",
                    data=data
                )
            return ChatResponse(reply=f"No delivery confirmation found with ID {identifier}")
        return ChatResponse(reply="Please provide a Delivery ID like: delivery <id>")

    # --- 9) Fallback ---
    log_activity(db, current_user.id, "chat_fallback", details=f"Unrecognized chat message: {raw}")
    return ChatResponse(reply="Sorry, I didn't understand that. Try 'help' to see what I can do.")