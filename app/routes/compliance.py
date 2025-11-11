from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.schemas import ComplianceStatusCreate, ComplianceStatusUpdate, ComplianceStatusOut
from app.crudy.compliance_crudy import (
    create_compliance_status,
    update_compliance_status,
    get_compliance_by_org_id
)
from app.dependencies import get_current_user
from app.dependencies import require_role
from app.models import User
from app.utilites.compliance_alert import generate_compliance_alerts
from app.models import ComplianceStatus
from app.utilites.logging import log_activity
from app.models import Organization
from typing import List
router = APIRouter(
    prefix="/compliance",
    tags=["Compliance"],
)

@router.post("/", response_model=ComplianceStatusOut, status_code=status.HTTP_201_CREATED)
def create_compliance(
    compliance_data: ComplianceStatusCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    ✅ Create compliance status for an organization.
    🔐 Only Admins can create, and only for their own organization.
    """

    # ✅ Enforce multi-tenant: Admins can only create for their own org
    if current_user.organization_id != compliance_data.organization_id:
        raise HTTPException(
            status_code=403,
            detail="Admins can only create compliance status for their own organization"
        )

    created = create_compliance_status(db, compliance_data)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=created.organization_id,
        action="compliance_created",
        details=f"Admin {current_user.name} created compliance record for Org ID {created.organization_id}"
    )

    return created


@router.get("/{org_id}", response_model=ComplianceStatusOut)
def get_compliance_by_org(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    📄 Get compliance status by organization ID.
    🔐 Access control:
    - regulator: can access orgs under their regulated country/state/region
    - admin: can access only their own organization
    - others: denied
    """
    # ❌ Clients and unrelated roles are denied
    if current_user.role not in ["admin", "regulator"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # 🛡 Admin: restrict to own organization
    if current_user.role == "admin" and current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Admins can only access their own organization")

    # 🛡 Regulator: only access organizations under their jurisdiction
    if current_user.role == "regulator":
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        if (
            org.regulated_country != current_user.regulated_country or
            org.regulated_state != current_user.regulated_state or
            org.regulated_region != current_user.regulated_region
        ):
            raise HTTPException(status_code=403, detail="Access denied: Outside your regulated region")

    # ✅ Fetch compliance
    compliance = get_compliance_by_org_id(db, org_id)
    if not compliance:
        raise HTTPException(status_code=404, detail="Compliance status not found")

    # 📝 Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=org_id,
        action="compliance_viewed",
        details=f"{current_user.role} {current_user.name} viewed compliance for Org ID {org_id}"
    )

    return compliance

@router.patch("/{status_id}", response_model=ComplianceStatusOut)
def update_compliance(
    status_id: UUID,
    updates: ComplianceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"]))
):
    """
    🛠 Update compliance status by status ID.
    🔐 Admin: only their own organization. Super Admin: any.
    """
    status = db.query(ComplianceStatus).filter(ComplianceStatus.id == status_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="Compliance status not found")

    # 🛡️ Admin: restrict to own organization
    if current_user.role == "admin" and current_user.organization_id != status.organization_id:
        raise HTTPException(status_code=403, detail="Admins can only update their own organization")

    # ✅ Perform update
    updated = update_compliance_status(db, status_id, updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update compliance status")

    # 📝 Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=updated.organization_id,
        action="compliance_updated",
        details=f"{current_user.role} {current_user.name} updated compliance ID {status_id} for Org {updated.organization_id}"
    )

    return updated

@router.get("/compliance/{org_id}/alerts")
def get_compliance_alerts(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"]))
):
    """
    🚨 Get compliance alerts for a specific organization.
    🔐 Admins only see their own org. Super Admins can see all.
    """
    # 🔐 Enforce multi-tenancy
    if current_user.role == "admin" and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=403,
            detail="Admins can only view alerts for their own organization"
        )

    compliance = db.query(ComplianceStatus).filter_by(organization_id=org_id).first()
    if not compliance:
        raise HTTPException(status_code=404, detail="Compliance record not found")

    alerts = generate_compliance_alerts(compliance)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=org_id,
        action="compliance_alerts_generated",
        details=f"{current_user.role} {current_user.name} generated compliance alerts for Org ID {org_id}"
    )

    return {
        "organization_id": str(org_id),
        "alerts": alerts
    }
    
@router.get("/regional", response_model=List[ComplianceStatusOut])
def get_regional_or_org_compliance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "regulator", "super_admin"]))
):
    """
    🌍 Get compliance statuses based on user role:
    - 🧩 Admin: only their own organization's compliance.
    - 🧭 Regulator: all organizations in their regulated region/country/state.
    - 🏛️ Super Admin: all organizations (global view).
    """
    query = db.query(ComplianceStatus)

    # 🧩 Admin → only their org
    if current_user.role == "admin":
        query = query.filter(ComplianceStatus.organization_id == current_user.organization_id)

    # 🧭 Regulator → all orgs under their jurisdiction
    elif current_user.role == "regulator":
        orgs = db.query(Organization).filter(
            Organization.regulated_country == current_user.regulated_country,
            Organization.regulated_state == current_user.regulated_state,
            Organization.regulated_region == current_user.regulated_region
        ).all()
        org_ids = [o.id for o in orgs]
        query = query.filter(ComplianceStatus.organization_id.in_(org_ids))

    # 🏛️ Super Admin → full access
    elif current_user.role == "super_admin":
        pass  # full access

    # 🚫 Others → denied
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    results = query.all()

    if not results:
        raise HTTPException(status_code=404, detail="No compliance records found")

    return results
    