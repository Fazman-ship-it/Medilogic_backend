from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app import models, schemas, config
from app.database import get_db
from app.dependencies import get_current_user
from app.dependencies import require_role
from typing import List,Optional
import os
from datetime import datetime
import os
import uuid
from fastapi import APIRouter, Form, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.email_utilites import send_email
from app.storage import S3Storage
from app.config import settings

router = APIRouter(prefix="/incidents", tags=["Incidents"]) 
storage = S3Storage()

@router.post("/submit", response_model=schemas.IncidentOut)
def submit_incident(
    title: str = Form(...),
    description: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Only admins can submit incidents
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only organization admins can submit incidents.")

    # ✅ Upload file to S3 (if provided)
    attachment_key = None
    if file:
        # Validate allowed extensions
        ext = os.path.splitext(file.filename)[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".pdf", ".docx"}:
            raise HTTPException(status_code=400, detail="File type not allowed")

        # Save to S3 (e.g., incidents/org_id/filename.ext)
        unique_filename = f"{uuid.uuid4()}{ext}"
        attachment_key = f"incidents/{current_user.organization_id}/{unique_filename}"
        storage.client.upload_fileobj(file.file, storage.bucket, attachment_key)

    # ✅ Create incident record
    new_incident = models.Incident(
        title=title,
        description=description,
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        attachment_url=attachment_key,  # store key only
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
        incidents = db.query(models.Incident).all()
    elif current_user.role == "regulator":
        incidents = db.query(models.Incident).join(models.Organization).filter(
            models.Organization.country == current_user.regulated_country,
            models.Organization.state == current_user.regulated_state,
            models.Organization.region == current_user.regulated_region
        ).all()
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view incidents.")

    # 🔄 Convert DB shape → API response
    result = []
    for inc in incidents:
        presigned_url = (
            storage.generate_download_url(inc.attachment_url)
            if inc.attachment_url else None
        )
        result.append(
            schemas.IncidentOut(
                id=inc.id,
                title=inc.title,
                description=inc.description,
                organization_id=inc.organization_id,
                submitted_by_id=inc.submitted_by_id,
                status=inc.status,
                created_at=inc.created_at,
                attachment_url=presigned_url,  # now real link
            )
        )
    return result

@router.post("/incidents/driver", response_model=schemas.IncidentOut)
def submit_incident_as_driver(
    title: str = Form(...),
    description: str = Form(...),
    incident_type: str = Form(...),
    location: str = Form(...),
    severity: str = Form(...),
    is_visible_to_regulator: bool = Form(False),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can submit incidents")

    # ✅ Upload to S3 (if file is attached)
    attachment_key = None
    if file:
        ext = os.path.splitext(file.filename)[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".pdf", ".docx"}:
            raise HTTPException(status_code=400, detail="File type not allowed")

        unique_filename = f"{uuid.uuid4()}{ext}"
        attachment_key = f"incidents/{current_user.organization_id}/{unique_filename}"

        storage.upload_fileobj(file.file, attachment_key)

    # ✅ Save to DB (store key only)
    new_incident = models.Incident(
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        title=title,
        description=description,
        incident_type=incident_type,
        location=location,
        severity=severity,
        is_visible_to_regulator=is_visible_to_regulator,
        attachment_url=attachment_key
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # ✅ Notifications (critical or regulator-visible only)
    recipients = db.query(models.User).filter(
        models.User.organization_id == current_user.organization_id,
        models.User.role.in_(["admin", "regulator"]),
        models.User.is_active == True,
        models.User.email.isnot(None)
    ).all()

    recipient_emails = [user.email for user in recipients if user.email]

    if recipient_emails and (severity.lower() == "critical" or is_visible_to_regulator):
        presigned_url = (
            storage.generate_download_url(attachment_key)
            if attachment_key else "None"
        )
        subject = f"🚨 New Incident from {current_user.full_name} - Severity: {severity.title()}"
        body = f"""
A new incident has been reported by {current_user.full_name} ({current_user.email}):

📝 Title: {title}
📍 Location: {location}
⚠️ Severity: {severity}
👁 Visible to Regulator: {"Yes" if is_visible_to_regulator else "No"}
🏢 Organization: {current_user.organization.name}
📎 Attachment: {presigned_url}

Description:
{description}

Please review this incident in the Medilogic Admin Panel.
"""
        send_email(subject, body, recipient_emails)

    return new_incident

@router.get("/incidents/admin", response_model=List[schemas.IncidentOut])
def get_org_incidents_for_admin(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view incidents")

    incidents = db.query(models.Incident).filter(
        models.Incident.organization_id == current_user.organization_id
    ).order_by(models.Incident.created_at.desc()).all()

    return incidents