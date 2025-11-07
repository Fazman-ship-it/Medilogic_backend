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
async def submit_incident(
    title: str = Form(...),
    description: str = Form(...),
    incident_type: str = Form(...),  # ✅ required field
    location: Optional[str] = Form(None),
    severity: Optional[str] = Form("low"),  # ✅ default value
    is_visible_to_regulator: Optional[bool] = Form(False),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Only admins can submit incidents
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only organization admins can submit incidents."
        )

    # ✅ Create the incident record
    new_incident = models.Incident(
        title=title,
        description=description,
        incident_type=incident_type,  # ✅ now included
        location=location,
        severity=severity,
        is_visible_to_regulator=is_visible_to_regulator,
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

            s3_key = await upload_file_to_s3_async(
                file,
                prefix=f"incidents/{current_user.organization_id}/{new_incident.id}"
            )

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
from uuid import UUID

@router.get("/{incident_id}", response_model=schemas.IncidentOut)
async def get_incident_detail(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 🔍 Find the incident
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # 🔒 Role-based access control
    if current_user.role == "super_admin":
        pass  # full access
    elif current_user.role == "regulator":
        # Only view incidents in their jurisdiction
        org = incident.organization
        if (
            org.country != current_user.regulated_country
            or org.state != current_user.regulated_state
            or org.region != current_user.regulated_region
        ):
            raise HTTPException(status_code=403, detail="Not authorized to view this incident")
    elif current_user.role in ["admin", "driver"]:
        # Only see incidents within their own organization
        if incident.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this incident")
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # ✅ Generate presigned URLs for attached files
    file_responses = []
    for f in incident.files:
        presigned_url = await generate_presigned_url_async(
            f.s3_key, expires_in=settings.PRESIGNED_EXPIRY
        )
        file_responses.append(
            schemas.IncidentFileOut(
                id=f.id,
                s3_key=presigned_url,
                file_type=f.file_type,
            )
        )

    # ✅ Return detailed info
    return schemas.IncidentOut(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        incident_type=incident.incident_type,
        severity=incident.severity,
        location=incident.location,
        is_visible_to_regulator=incident.is_visible_to_regulator,
        organization_id=incident.organization_id,
        submitted_by_id=incident.submitted_by_id,
        status=incident.status,
        created_at=incident.created_at,
        files=file_responses,
        updated_at=incident.updated_at,
    )

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

        subject = f"🚨 New Incident from {current_user.name} - Severity: {severity.title()}"
        body = f"""
A new incident has been reported by {current_user.name} ({current_user.email}):

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

    # ✅ Sort by latest updates first
    incidents = db.query(models.Incident).filter(
        models.Incident.organization_id == current_user.organization_id
    ).order_by(models.Incident.updated_at.desc()).all()

    return incidents
    
@router.get("/my-submissions", response_model=List[schemas.IncidentOut])
def get_my_incidents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Only admins can access their organization's incidents
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view their submitted incidents.")

    incidents = (
        db.query(models.Incident)
        .filter(models.Incident.organization_id == current_user.organization_id)
        .order_by(models.Incident.created_at.desc())
        .all()
    )

    return incidents
    
@router.get("/driver/my-submissions", response_model=List[schemas.IncidentOut])
def get_driver_incidents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can view their submitted incidents.")

    # ✅ Sort by latest updated incidents
    incidents = (
        db.query(models.Incident)
        .filter(models.Incident.submitted_by_id == current_user.id)
        .order_by(models.Incident.updated_at.desc())
        .all()
    )

    return incidents
    
from fastapi import APIRouter, Depends, HTTPException, Body,Form,File
from sqlalchemy.orm import Session
from uuid import UUID
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user  
from app.dependencies import require_role
from typing import List,Optional
from datetime import datetime

@router.get("/{incident_id}", response_model=schemas.IncidentOut)
async def get_incident_details(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    org = incident.organization  # ✅ For jurisdiction checks

    # 🔒 Role-based access control with jurisdiction
    if current_user.role == "super_admin":
        pass  # full unrestricted access

    elif current_user.role == "regulator":
        # ✅ Jurisdiction-based restriction
        if (
            (current_user.regulated_country and org.country != current_user.regulated_country)
            or (current_user.regulated_state and org.state != current_user.regulated_state)
            or (current_user.regulated_region and org.region != current_user.regulated_region)
        ):
            raise HTTPException(status_code=403, detail="Not authorized to view this incident")

        # ✅ Regulator can only see visible or escalated incidents
        if not (incident.is_visible_to_regulator or incident.status == "escalated"):
            raise HTTPException(
                status_code=403,
                detail="You can only view escalated or regulator-visible incidents."
            )

    elif current_user.role == "admin":
        # ✅ Admin can only see incidents within their own organization
        if incident.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this incident")

    elif current_user.role == "driver":
        # ✅ Driver can only see their own incidents
        if incident.submitted_by_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only view your own incidents.")

    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # ✅ Generate presigned URLs for attached files
    file_responses = []
    for f in incident.files:
        presigned_url = await generate_presigned_url_async(
            f.s3_key, expires_in=settings.PRESIGNED_EXPIRY
        )
        file_responses.append(
            schemas.IncidentFileOut(id=f.id, s3_key=presigned_url, file_type=f.file_type)
        )

    # ✅ Return detailed incident info
    return schemas.IncidentOut(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        incident_type=incident.incident_type,
        severity=incident.severity,
        location=incident.location,
        is_visible_to_regulator=incident.is_visible_to_regulator,
        organization_id=incident.organization_id,
        submitted_by_id=incident.submitted_by_id,
        status=incident.status,
        created_at=incident.created_at,
        files=file_responses,
        updated_at=incident.updated_at,
    )
    
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from uuid import UUID
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

@router.patch("/{incident_id}/status")
def update_incident_status(
    incident_id: UUID,
    status: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    allowed_statuses = ["pending", "under_review", "escalated", "resolved", "closed"]
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # 🔒 Role-based control with transition logic
    if current_user.role == "admin":
        allowed_transitions = {
            "pending": ["under_review"],
            "under_review": ["escalated", "resolved"],
        }
    elif current_user.role == "regulator":
        allowed_transitions = {
            "escalated": ["resolved"],
            "resolved": ["closed"],
        }
    elif current_user.role == "super_admin":
        allowed_transitions = {s: allowed_statuses for s in allowed_statuses}  # full override
    else:
        raise HTTPException(status_code=403, detail="You cannot update incident status.")

    current_status = incident.status
    next_allowed = allowed_transitions.get(current_status, [])

    if status not in next_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from '{current_status}' to '{status}' for your role."
        )

    # ✅ Update status (this will automatically update 'updated_at' due to onupdate=func.now())
    incident.status = status
    db.commit()
    db.refresh(incident)

    # ✅ Return with updated timestamp
    return {
        "message": f"Incident status updated to {status}",
        "incident": {
            "id": incident.id,
            "status": incident.status,
            "updated_at": incident.updated_at
        }
    }
    
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from uuid import UUID
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

    
@router.patch("/{incident_id}/escalate")
def toggle_incident_escalation(
    incident_id: UUID,
    escalated: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Allows authorized users (admin, regulator, super_admin) to toggle an incident's escalation status.
    Automatically updates incident status to 'escalated' or 'under_review'.
    """

    # 🔍 Find the incident
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # 🔒 Role-based control
    if current_user.role not in ["admin", "regulator", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to change escalation status")

    # ✅ Update escalation flag and status
    incident.escalated = escalated
    if escalated:
        incident.status = "escalated"
    else:
        # If it's de-escalated, move it back to "under_review" for admin review
        incident.status = "under_review"

    db.commit()
    db.refresh(incident)

    return {
        "message": f"Incident escalation status set to {escalated}",
        "incident": {
            "id": incident.id,
            "status": incident.status,
            "escalated": incident.escalated,
            "updated_at": incident.updated_at,
        },
    }
    
from sqlalchemy import or_,desc
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from app import models, schemas, settings
from app.dependencies import get_db, get_current_user

async def get_all_incidents_for_regulator(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Role check
    if current_user.role not in ["regulator", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Base query
    query = db.query(models.Incident).join(models.Organization)

    # ✅ Super admin can view all incidents
    if current_user.role == "super_admin":
        query = query.order_by(desc(models.Incident.updated_at))
    else:
        # ✅ Regulator — filter by jurisdiction
        filters = []

        if current_user.regulated_country:
            filters.append(models.Organization.country == current_user.regulated_country)
        if current_user.regulated_state:
            filters.append(models.Organization.state == current_user.regulated_state)
        if current_user.regulated_region:
            filters.append(models.Organization.region == current_user.regulated_region)

        # Regulator sees only visible or escalated incidents
        filters.append(
            or_(
                models.Incident.is_visible_to_regulator == True,
                models.Incident.status == "escalated"
            )
        )

        query = query.filter(*filters).order_by(desc(models.Incident.updated_at))

    # ✅ Execute query
    incidents = query.all()

    # ✅ Generate presigned URLs for files
    results = []
    for incident in incidents:
        file_responses = []
        for f in incident.files:
            presigned_url = await generate_presigned_url_async(
                f.s3_key, expires_in=settings.PRESIGNED_EXPIRY
            )
            file_responses.append(
                schemas.IncidentFileOut(
                    id=f.id,
                    s3_key=presigned_url,
                    file_type=f.file_type
                )
            )

        results.append(
            schemas.IncidentOut(
                id=incident.id,
                title=incident.title,
                description=incident.description,
                incident_type=incident.incident_type,
                severity=incident.severity,
                location=incident.location,
                is_visible_to_regulator=incident.is_visible_to_regulator,
                organization_id=incident.organization_id,
                submitted_by_id=incident.submitted_by_id,
                status=incident.status,
                created_at=incident.created_at,
                updated_at=incident.updated_at,
                files=file_responses,
            )
        )

    return results