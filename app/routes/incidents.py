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
from app.config import settings

router = APIRouter(prefix="/incidents", tags=["Incidents"])

from app.config import settings
from app.utilites.storage_utilites import upload_file_to_s3_async  # ✅ import your new helper

@router.post("/submit", response_model=schemas.IncidentOut)
async def submit_incident(   # ✅ must be async now because S3 upload is async
    title: str = Form(...),
    description: str = Form(...),
    files: List[UploadFile] = File(None),  # ✅ allow multiple files
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Only admins can submit incidents
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only organization admins can submit incidents.")

    # ✅ Create incident record first
    new_incident = models.Incident(
        title=title,
        description=description,
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        status="pending"
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # ✅ Upload files if provided
    if files:
        for file in files:
            ext = os.path.splitext(file.filename)[-1].lower()
            if ext not in {".jpg", ".jpeg", ".png", ".pdf", ".docx"}:
                raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

            # ✅ use async uploader
            s3_key = await upload_file_to_s3_async(
                file,
                prefix=f"incidents/{current_user.organization_id}/{new_incident.id}"
            )

            # Save to IncidentFile
            db.add(models.IncidentFile(
                incident_id=new_incident.id,
                s3_key=s3_key,
                file_type=ext.replace(".", "")
            ))

        db.commit()

    db.refresh(new_incident)
    return new_incident

from app.config import settings
from app.utilites.storage_utilites import generate_presigned_url_async  # ✅ use new async helper

@router.get("/", response_model=List[schemas.IncidentOut])
async def get_incidents(   # ✅ must be async now
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 🔒 Role-based visibility
    if current_user.role == "super_admin":
        incidents = db.query(models.Incident).all()
    elif current_user.role == "regulator":
        incidents = (
            db.query(models.Incident)
            .join(models.Organization)
            .filter(
                models.Organization.country == current_user.regulated_country,
                models.Organization.state == current_user.regulated_state,
                models.Organization.region == current_user.regulated_region,
            )
            .all()
        )
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view incidents.")

    # 🔄 Build API response (with presigned URLs for files)
    result = []
    for inc in incidents:
        file_responses = []
        for f in inc.files:
            presigned_url = await generate_presigned_url_async(   # ✅ async call
                f.s3_key,
                expires_in=settings.PRESIGNED_EXPIRY   # ✅ use expiry from config
            )
            file_responses.append(
                schemas.IncidentFileOut(
                    id=f.id,
                    s3_key=presigned_url,  # return URL, not raw key
                    file_type=f.file_type,
                )
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
                files=file_responses,
            )
        )

    return result

@router.post("/incidents/driver", response_model=schemas.IncidentOut)
async def submit_incident_as_driver(   # ✅ must be async now
    title: str = Form(...),
    description: str = Form(...),
    incident_type: str = Form(...),
    location: str = Form(...),
    severity: str = Form(...),
    is_visible_to_regulator: bool = Form(False),
    files: List[UploadFile] = File([]),  # ✅ support multiple files
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can submit incidents")

    # ✅ Create incident record first
    new_incident = models.Incident(
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        title=title,
        description=description,
        incident_type=incident_type,
        location=location,
        severity=severity,
        is_visible_to_regulator=is_visible_to_regulator,
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # ✅ Handle file uploads (store in IncidentFile table)
    for file in files:
        ext = os.path.splitext(file.filename)[-1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".pdf", ".docx"}:
            raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

        # Upload to S3 (async helper)
        s3_key = await upload_file_to_s3_async(
            file,
            prefix=f"incidents/{current_user.organization_id}/{new_incident.id}"
        )

        db.add(models.IncidentFile(
            incident_id=new_incident.id,
            s3_key=s3_key,
            file_type=ext.replace(".", ""),  # e.g., pdf, jpg
        ))

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
        file_urls = []
        for f in new_incident.files:
            presigned_url = await generate_presigned_url_async(   # ✅ async download URL
                f.s3_key,
                expires_in=settings.PRESIGNED_EXPIRY
            )
            file_urls.append(presigned_url)

        subject = f"🚨 New Incident from {current_user.full_name} - Severity: {severity.title()}"
        body = f"""
A new incident has been reported by {current_user.full_name} ({current_user.email}):

📝 Title: {title}
📍 Location: {location}
⚠️ Severity: {severity}
👁 Visible to Regulator: {"Yes" if is_visible_to_regulator else "No"}
🏢 Organization: {current_user.organization.name}
📎 Attachments: {", ".join(file_urls) if file_urls else "None"}

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