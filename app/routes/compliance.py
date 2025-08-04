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

router = APIRouter(
    prefix="/compliance",
    tags=["Compliance"],
)

@router.post("/", response_model=ComplianceStatusOut, status_code=status.HTTP_201_CREATED)
def create_compliance(
    compliance_data: ComplianceStatusCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"]))
):
    """
    ✅ Create compliance status for an organization.
    🔐 Admin and Super Admin only.
    """
    return create_compliance_status(db, compliance_data)

@router.get("/{org_id}", response_model=ComplianceStatusOut)
def get_compliance_by_org(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    📄 Get compliance status by organization ID.
    🔐 Access control:
    - super_admin: can access all orgs
    - admin/client: can access only their own org
    - others: denied
    """
    # Super admin has access to all orgs
    if current_user.role not in ["super_admin", "admin", "client"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Admins and clients can only view their own organization
    if current_user.role in ["admin", "client"] and current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied for this organization")

    compliance = get_compliance_by_org_id(db, org_id)
    if not compliance:
        raise HTTPException(status_code=404, detail="Compliance status not found")
    
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
    🔐 Admin and Super Admin only.
    """
    updated = update_compliance_status(db, status_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Compliance status not found")
    return updated