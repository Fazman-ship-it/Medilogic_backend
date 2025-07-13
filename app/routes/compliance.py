from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.dependencies import get_db, get_current_user
from app.utilites.logging import log_activity
import csv
import io
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.models import Organization, ComplianceStatus

router = APIRouter(prefix="/compliance", tags=["Compliance"])

@router.post("/", response_model=schemas.ComplianceStatusOut)
def create_compliance_status(
    data: schemas.ComplianceStatusCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to create compliance status")

    existing = db.query(models.ComplianceStatus).filter_by(organization_id=data.organization_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Compliance record already exists")

    record = models.ComplianceStatus(**data.dict())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{org_id}", response_model=schemas.ComplianceStatusOut)
def update_compliance_status(
    org_id: int,
    update: schemas.ComplianceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    record = db.query(models.ComplianceStatus).filter_by(organization_id=org_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Compliance record not found")

    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to update")

    # Track what was updated
    changes = []
    for key, value in update.dict(exclude_unset=True).items():
        old = getattr(record, key)
        if old != value:
            changes.append(f"{key}: {old} ➝ {value}")
        setattr(record, key, value)

    db.commit()
    db.refresh(record)

    if changes:
        log_activity(
            db=db,
            user_id=current_user.id,
            action="update_compliance_status",
            details="; ".join(changes),
            organization_id=org_id
        )

    return record


@router.get("/{org_id}", response_model=schemas.ComplianceStatusOut)
def get_compliance_status(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    record = db.query(models.ComplianceStatus).filter_by(organization_id=org_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Compliance status not found")
    return record


@router.get("/regulator/export-compliance", response_class=StreamingResponse)
def export_regulator_compliance_data(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # ✅ Role check
    if current_user.role != "regulator":
        raise HTTPException(status_code=403, detail="Only regulators can export compliance data.")

    # 🔍 Filter organizations under this regulator
    orgs = db.query(Organization).filter(
        Organization.country == current_user.regulated_country,
        Organization.state == current_user.regulated_state,
        Organization.region == current_user.regulated_region
    ).all()

    # 🧾 Prepare CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Organization",
        "ISO 27001 Certified",
        "NHS DSP Toolkit Complete",
        "Cyber Essentials Ready",
        "Waste License Present",
        "Last Audit Date"
    ])

    for org in orgs:
        comp = org.compliance_status
        writer.writerow([
            org.name,
            "Yes" if comp and comp.iso_27001_certified else "No",
            "Yes" if comp and comp.nhs_dsp_toolkit_complete else "No",
            "Yes" if comp and comp.cyber_essentials_ready else "No",
            "Yes" if comp and comp.has_waste_license else "No",
            comp.last_audit_date.strftime('%Y-%m-%d') if comp and comp.last_audit_date else "N/A"
        ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=regulator_compliance_export.csv"
        }
    )