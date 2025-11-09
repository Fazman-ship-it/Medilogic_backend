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
        status="pending",
        escalated=False
        
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
    
@router.post("/incidents/driver", response_model=schemas.IncidentOut)
async def submit_incident_as_driver(
    title: str = Form(...),
    description: str = Form(...),
    incident_type: str = Form(...),
    location: str = Form(...),
    severity: str = Form(...),
    files: List[UploadFile] = File([]),  # ✅ support multiple files
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🔒 Role validation
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can submit incidents")

    # ✅ Create the incident (always pending at creation)
    new_incident = models.Incident(
        organization_id=current_user.organization_id,
        submitted_by_id=current_user.id,
        title=title,
        description=description,
        incident_type=incident_type,
        location=location,
        severity=severity,
        status="pending",
    )

    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # ✅ Handle file uploads
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
            file_type=ext.replace(".", ""),
        ))

    db.commit()
    db.refresh(new_incident)

    # ✅ Notify admins within the same organization
    admin_recipients = db.query(models.User).filter(
        models.User.organization_id == current_user.organization_id,
        models.User.role == "admin",
        models.User.is_active == True,
        models.User.email.isnot(None)
    ).all()

    admin_emails = [admin.email for admin in admin_recipients if admin.email]

    # 🔔 Send email only if severity is critical
    if admin_emails and severity.lower() == "critical":
        file_urls = []
        for f in new_incident.files:
            presigned_url = await generate_presigned_url_async(
                f.s3_key,
                expires_in=settings.PRESIGNED_EXPIRY
            )
            file_urls.append(presigned_url)

        subject = f"🚨 New Critical Incident from {current_user.name}"
        body = f"""
A new critical incident has been reported by {current_user.name} ({current_user.email}):

📝 Title: {title}
📍 Location: {location}
⚠️ Severity: {severity.title()}
🏢 Organization: {current_user.organization.name}
📎 Attachments: {", ".join(file_urls) if file_urls else "None"}

Description:
{description}

Please review this incident in the Medilogic Admin Panel.
"""
        send_email(subject, body, admin_emails)

    return new_incident
    
from sqlalchemy import or_,desc
from fastapi import HTTPException, Depends, Query 
from sqlalchemy.orm import Session
from app import models, schemas
from app.dependencies import get_current_user,require_role
from app.database import get_db
from app.config import settings
from app.utilites.storage_utilites import generate_presigned_url_async  # ✅ use new async helper
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func
from typing import List, Optional
from app import models, schemas
from pydantic import BaseModel
from app.schemas import PaginatedIncidents

@router.get("/regulator", response_model=PaginatedIncidents)
def get_incidents_for_regulator_paginated(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="Number of incidents to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of incidents to return")
):
    # 🔒 Role check
    if current_user.role not in ["regulator", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Base query
    query = db.query(models.Incident)

    # Regulators see only incidents in their jurisdiction
    if current_user.role == "regulator":
        query = query.join(models.Organization)
        if current_user.regulated_country:
            query = query.filter(models.Organization.country == current_user.regulated_country)
        if current_user.regulated_state:
            query = query.filter(models.Organization.state == current_user.regulated_state)
        if current_user.regulated_region:
            query = query.filter(models.Organization.region == current_user.regulated_region)

    # Total count before pagination
    total_count = query.count()

    # Apply sorting and pagination
    incidents = query.order_by(models.Incident.updated_at.desc()) \
                     .offset(skip).limit(limit) \
                     .all()

    # Return in the same style as your trips endpoint
    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": incidents  # FastAPI will automatically convert to IncidentOut
    }
    
@router.get("/incidents/admin", response_model=schemas.PaginatedIncidents)
def get_org_incidents_for_admin_paginated(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="Number of incidents to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of incidents to return")
):
    """
    Returns all incidents submitted by drivers within the admin's organization.
    Only accessible to admins.
    """
    # 🔒 Role check
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view organization incidents.")

    # ✅ Query only driver-submitted incidents in the admin's organization
    query = (
        db.query(models.Incident)
        .join(models.User, models.Incident.submitted_by_id == models.User.id)
        .filter(
            models.User.role == "driver",
            models.Incident.organization_id == current_user.organization_id
        )
    )

    total_count = query.count()

    incidents = query.order_by(models.Incident.updated_at.desc()) \
                     .offset(skip).limit(limit) \
                     .all()

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": incidents
    }
    

@router.get("/my-submissions", response_model=schemas.PaginatedIncidents)
def get_my_incidents_paginated(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="Number of incidents to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of incidents to return")
):
    """
    Returns all incidents submitted by the current admin to regulators.
    Only accessible to admins.
    """
    # 🔒 Role check
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view their submitted incidents.")

    # ✅ Filter by current user's own submissions
    query = db.query(models.Incident).filter(
        models.Incident.submitted_by_id == current_user.id
    )

    total_count = query.count()

    incidents = query.order_by(models.Incident.created_at.desc()) \
                     .offset(skip).limit(limit) \
                     .all()

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": incidents
    }
    
@router.get("/driver/my-submissions", response_model=schemas.PaginatedIncidents)
def get_driver_incidents_paginated(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="Number of incidents to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of incidents to return")
):
    # 🔒 Role check
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can view their submitted incidents.")

    # ✅ Base query scoped to the current driver
    query = db.query(models.Incident).filter(
        models.Incident.submitted_by_id == current_user.id
    )

    # ✅ Total count before pagination
    total_count = query.count()

    # ✅ Apply sorting and pagination
    incidents = query.order_by(models.Incident.updated_at.desc()) \
                     .offset(skip).limit(limit) \
                     .all()

    # ✅ Return in the standard paginated format
    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": incidents  # Pydantic converts each Incident to IncidentOut automatically
    }
    
    
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from uuid import UUID
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.logging import log_activity

@router.patch("/{incident_id}/status")
def update_incident_status(
    incident_id: UUID,
    status: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    ✅ Update an incident's status with role-based allowed transitions:
    - Admin: can move pending → under_review → escalated/resolved
    - Driver: can move under_review → on_site → resolved
    - Regulator: can move escalated → resolved → closed
    - Super_admin: can set any status
    """

    allowed_statuses = ["pending", "under_review", "on_site", "escalated", "resolved", "closed"]

    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # 🔍 Fetch the incident
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    current_status = incident.status

    # 🔒 Define role-based allowed transitions
    if current_user.role == "admin":
        allowed_transitions = {
            "pending": ["under_review"],
            "under_review": ["escalated", "resolved"],
            "escalated": ["resolved"]
        }
    elif current_user.role == "driver":
        allowed_transitions = {
            "under_review": ["on_site"],
            "on_site": ["resolved"]
        }
    elif current_user.role == "regulator":
        allowed_transitions = {
            "escalated": ["resolved"],
            "resolved": ["closed"]
        }
    elif current_user.role == "super_admin":
        allowed_transitions = {s: allowed_statuses for s in allowed_statuses}
    else:
        raise HTTPException(status_code=403, detail="You cannot update incident status.")

    # ✅ Check if the transition is valid
    next_allowed = allowed_transitions.get(current_status, [])
    if status not in next_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from '{current_status}' to '{status}' for role '{current_user.role}'."
        )

    # 🔁 Update the status
    incident.status = status
    db.commit()
    db.refresh(incident)

    # 📝 Log the activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="incident_status_updated",
        details=f"{current_user.role.capitalize()} {current_user.name} changed status of '{incident.title}' from '{current_status}' to '{status}'"
    )

    # ✅ Return updated incident info
    return {
        "message": f"Incident status updated to '{status}'",
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
from app.utilites.logging import log_activity

@router.patch("/{incident_id}/toggle-escalation")
def toggle_incident_escalation(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ✅ Toggle an incident's escalation status (True ↔ False)
    - Admins or regulators can toggle it
    - Others will get a 403 error
    """
    # 🔒 Role check
    if current_user.role not in ["admin", "regulator", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to toggle escalation")

    # 🔍 Find incident within the user’s organization (for data safety)
    incident = (
        db.query(models.Incident)
        .filter(models.Incident.id == incident_id)
        .first()
    )

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # 🔁 Toggle escalation status
    incident.escalated = not incident.escalated
    db.commit()
    db.refresh(incident)

    # 📝 Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="incident_escalation_toggled",
        details=f"{current_user.role.capitalize()} {current_user.name} set incident '{incident.title}' escalation to {incident.escalated}",
    )

    return {
        "message": f"Incident escalation toggled to {incident.escalated}",
        "incident_id": str(incident.id),
        "escalated": incident.escalated,
    }
    
    
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
