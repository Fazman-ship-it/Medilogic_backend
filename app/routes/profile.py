from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import models
from app.dependencies import get_db, get_current_user   
router = APIRouter(
    prefix="/profile",
    tags=["Profile"]
)

@router.get("", summary="View your profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Get the organization
    organization = db.query(models.Organization).filter_by(id=current_user.organization_id).first()

    return {
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "organization": {
            "id": organization.id if organization else None,
            "name": organization.name if organization else None,
            "invite_code": organization.invite_code if organization else None
        }
    }