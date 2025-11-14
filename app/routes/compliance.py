from fastapi import APIRouter, Depends, HTTPException, status,Query 
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.schemas import ComplianceStatusCreate, ComplianceStatusUpdate, ComplianceStatusOut,PaginatedComplianceStatus
from app.crudy.compliance_crudy import (
    create_compliance_status,
    update_compliance_status,
    get_compliance_by_org_id
)
from app.dependencies import get_current_user,require_role
from app.models import User
from app.utilites.compliance_alert import generate_compliance_alerts
from app.models import ComplianceStatus
from app.utilites.logging import log_activity
from app.models import Organization,User
from typing import List
from app import schemas,models
from app.crud import create_compliance_status,update_compliance_status

router = APIRouter(
    prefix="/compliance",
    tags=["Compliance"],
)


@router.post("/", response_model=schemas.ComplianceStatusOut, status_code=status.HTTP_201_CREATED)
def create_compliance(
    compliance_data: schemas.ComplianceStatusCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # ✅ directly get current user
):
    """
    Create a compliance status record for the admin's own organization.
    Only accessible to Admins.
    """

    # 🔒 Ensure only admins can access
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create compliance records."
        )

    # ✅ Tenant isolation: assign the admin's organization
    compliance_data.organization_id = current_user.organization_id

    # ✅ Check if a compliance record already exists for this organization
    existing = db.query(models.ComplianceStatus).filter(
        models.ComplianceStatus.organization_id == current_user.organization_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A compliance record already exists for this organization."
        )

    # ✅ Create compliance record
    created = create_compliance_status(db, compliance_data)

    # ✅ Log activity for auditing
    log_activity(
        db=db,
        user_id=current_user.id,
        action="compliance_created",
        details=f"Admin {current_user.name} created a compliance record for their organization."
    )

    return created
    

@router.get("/regional", response_model=PaginatedComplianceStatus)
def get_regional_or_org_compliance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ✅ use get_current_user
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
):
    """
    🌍 Get compliance statuses based on user role, with pagination:
    - 🧩 Admin: only their own organization's compliance.
    - 🧭 Regulator: all organizations in their jurisdiction (country/state/region).
    - 🏛️ Super Admin: all organizations globally.
    """

    # 🔐 Allow only specific roles
    allowed_roles = ["admin", "regulator", "super_admin"]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only admins, regulators, or super admins can view compliance records."
        )

    query = db.query(models.ComplianceStatus)

    # 🧩 Admin → only their organization
    if current_user.role == "admin":
        query = query.filter(models.ComplianceStatus.organization_id == current_user.organization_id)

    # 🧭 Regulator → organizations in their jurisdiction
    elif current_user.role == "regulator":
        org_query = db.query(models.Organization)
        if current_user.regulated_country:
            org_query = org_query.filter(models.Organization.country == current_user.regulated_country)
        if current_user.regulated_state:
            org_query = org_query.filter(models.Organization.state == current_user.regulated_state)
        if current_user.regulated_region:
            org_query = org_query.filter(models.Organization.region == current_user.regulated_region)

        orgs = org_query.all()
        org_ids = [o.id for o in orgs]
        query = query.filter(models.ComplianceStatus.organization_id.in_(org_ids))

    # 🏛️ Super Admin → all organizations (no filter)
    elif current_user.role == "super_admin":
        pass

    total_count = query.count()
    results = query.offset(skip).limit(limit).all()

    # ✅ Enrich results with organization names
    enriched_results = []
    for compliance in results:
        org = db.query(models.Organization).filter(models.Organization.id == compliance.organization_id).first()
        enriched_results.append(
            schemas.ComplianceStatusOut(
                **compliance.__dict__,
                organization_name=org.name if org else None
            )
        )

    if not enriched_results:
        raise HTTPException(status_code=404, detail="No compliance records found")

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": enriched_results
    }
        

@router.get("/{org_id}", response_model=ComplianceStatusOut)
def get_compliance_by_org(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ❌ Block irrelevant roles
    if current_user.role not in ["admin", "regulator"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # 🛡 Admin can only access their own org
    if current_user.role == "admin":
        if current_user.organization_id != org_id:
            raise HTTPException(
                status_code=403,
                detail="Admins can only access their own organization"
            )

    # 🛡 Regulator restrictions
    if current_user.role == "regulator":
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        if (
            (current_user.regulated_country and org.country != current_user.regulated_country) or
            (current_user.regulated_state and org.state != current_user.regulated_state) or
            (current_user.regulated_region and org.region != current_user.regulated_region)
        ):
            raise HTTPException(
                status_code=403,
                detail="Access denied: Outside your regulated jurisdiction"
            )

    # Fetch compliance
    compliance = get_compliance_by_org_id(db, org_id)
    if not compliance:
        raise HTTPException(status_code=404, detail="Compliance status not found")

    # Log
    log_activity(
        db=db,
        user_id=current_user.id,
        action="compliance_viewed",
        details=f"{current_user.role} {current_user.name} viewed compliance for Org ID {org_id}"
    )

    return compliance

@router.patch("/{status_id}", response_model=schemas.ComplianceStatusOut)
def update_compliance(
    status_id: UUID,
    updates: schemas.ComplianceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # ✅ switched from require_role()
):
    """
    🛠 Update compliance status by status ID.
    🔐 Admin: only their own organization.
    🏛 Super Admin: can update any compliance record.
    """

    # ✅ Fetch record
    status = db.query(models.ComplianceStatus).filter(models.ComplianceStatus.id == status_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="Compliance status not found")

    # 🔐 Allow only admins or super admins
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only admins or super admins can update compliance records."
        )

    # 🧩 Admins can only update their own organization
    if current_user.role == "admin" and current_user.organization_id != status.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only update compliance for their own organization."
        )

    # ✅ Perform the update
    updated = update_compliance_status(db, status_id, updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update compliance status")

    # 📝 Log the update activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="compliance_updated",
        details=f"{current_user.role} {current_user.name} updated compliance ID {status_id} for Org {updated.organization_id}"
    )

    return updated

@router.get("/compliance/{org_id}/alerts")
def get_compliance_alerts(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    🚨 Get compliance alerts for a specific organization.
    🔐 Admins: only their own org.
    🏛 Super Admins: can view all.
    """

    # Only admins or super admins allowed
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only admins or super admins can view compliance alerts."
        )

    # Admins restricted to their own organization
    if current_user.role == "admin" and str(current_user.organization_id) != str(org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only view alerts for their own organization."
        )

    # Fetch compliance record
    compliance = db.query(models.ComplianceStatus).filter_by(organization_id=org_id).first()
    if not compliance:
        raise HTTPException(status_code=404, detail="Compliance record not found")

    # Generate alerts
    alerts = generate_compliance_alerts(compliance)

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="compliance_alerts_generated",
        details=f"{current_user.role} {current_user.name} generated compliance alerts for Org ID {org_id}"
    )

    return {
        "organization_id": str(org_id),
        "alerts": alerts
    }
    