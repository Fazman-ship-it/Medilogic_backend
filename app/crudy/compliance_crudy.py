from sqlalchemy.orm import Session
from uuid import UUID
from app.models import ComplianceStatus
from app.schemas import ComplianceStatusCreate, ComplianceStatusUpdate

def create_compliance_status(db: Session, data: ComplianceStatusCreate):
    db_status = ComplianceStatus(**data.dict())
    db.add(db_status)
    db.commit()
    db.refresh(db_status)
    return db_status

def get_compliance_by_org_id(db: Session, org_id: UUID):
    return db.query(ComplianceStatus).filter(ComplianceStatus.organization_id == org_id).first()

def update_compliance_status(db: Session, status_id: UUID, updates: ComplianceStatusUpdate):
    db_status = db.query(ComplianceStatus).filter(ComplianceStatus.id == status_id).first()
    if not db_status:
        return None
    for field, value in updates.dict(exclude_unset=True).items():
        setattr(db_status, field, value)
    db.commit()
    db.refresh(db_status)
    return db_status