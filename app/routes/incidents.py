from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.dependencies import require_role
from typing import List,Optional
import os
from datetime import datetime

router = APIRouter(prefix="/incidents", tags=["Incidents"]) 

@router.post("/submit", response_model=schemas.IncidentOut)
def submit_incident(
    title: str = Form(...),
    description: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Only admins can submit incidents
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only organization admins can submit incidents.")

    # 📂 Handle optional file upload
    attachment_url = None
    if file:
        upload_folder = "static/incidents"
        os.makedirs(upload_folder, exist_ok=True)  # Make sure the folder exists
        file_path = os.path.join(upload_folder, file.filename)
        
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        attachment_url = file_path  # Store the relative file path

    # 📝 Save the incident
    new_incident = models.Incident(
        title=title,
        description=description,
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        attachment_url=attachment_url,
        status="pending",
        created_at=datetime.utcnow()
    )

    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    return new_incident


@router.get("/", response_model=List[schemas.IncidentOut])
def get_incidents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "super_admin":
        # Super admin can view all incidents
        return db.query(models.Incident).all()

    elif current_user.role == "regulator":
        # Regulator can only view incidents from their region
        return db.query(models.Incident).join(models.Organization).filter(
            models.Organization.country == current_user.regulated_country,
            models.Organization.state == current_user.regulated_state,
            models.Organization.region == current_user.regulated_region
        ).all()

    else:
        # Other roles cannot view incidents
        raise HTTPException(status_code=403, detail="Not authorized to view incidents.")

import os
import uuid
from app.utilites.email_utilites import send_email
from sqlalchemy import or_

@router.post("/incidents/driver", response_model=schemas.IncidentOut)
def submit_incident_as_driver(
    title: str = Form(...),
    description: str = Form(...),
    incident_type: str = Form(...),
    location: str = Form(...),
    severity: str = Form(...),  # "low", "moderate", "critical"
    is_visible_to_regulator: bool = Form(False),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can submit incidents")

    # Save file if present
    attachment_url = None
    if file:
        upload_folder = "static/incidents"
        os.makedirs(upload_folder, exist_ok=True)  # Ensure directory exists

        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[-1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_folder, unique_filename)

        # Save the file
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        # Return public-facing path
        attachment_url = f"/static/incidents/{unique_filename}"

    # Create incident record
    new_incident = models.Incident(
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        title=title,
        description=description,
        incident_type=incident_type,
        location=location,
        severity=severity,
        is_visible_to_regulator=is_visible_to_regulator,
        attachment_url=attachment_url
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # 🔔 Email notification to admins and regulators in the same organization
    recipients = db.query(models.User).filter(
        models.User.organization_id == current_user.organization_id,
        models.User.role.in_(["admin", "regulator"]),
        models.User.is_active == True,
        models.User.email.isnot(None)
    ).all()

    recipient_emails = [user.email for user in recipients if user.email]

    if recipient_emails and (severity.lower() == "critical" or is_visible_to_regulator):
        subject = f"🚨 New Incident from {current_user.full_name} - Severity: {severity.title()}"
        body = f"""
A new incident has been reported by {current_user.full_name} ({current_user.email}):

📝 Title: {title}
📍 Location: {location}
⚠️ Severity: {severity}
👁 Visible to Regulator: {"Yes" if is_visible_to_regulator else "No"}
🏢 Organization: {current_user.organization.name}
📎 Attachment: {attachment_url if attachment_url else "None"}

Description:
{description}

Please review this incident in the Medilogic Admin Panel.
"""
        send_email(subject, body, recipient_emails)

    return new_incident


@router.get("/incidents/admin", response_model=list[schemas.IncidentOut])
def get_org_incidents_for_admin(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Only allow admins
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view incidents")

    # ✅ Fetch incidents within the admin's organization
    incidents = db.query(models.Incident).filter(
        models.Incident.organization_id == current_user.organization_id
    ).order_by(models.Incident.created_at.desc()).all()

    return incidents