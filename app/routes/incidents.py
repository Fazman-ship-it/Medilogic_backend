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


