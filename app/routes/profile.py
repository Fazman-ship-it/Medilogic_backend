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

    # Base org info for all roles
    org_data = {
        "id": organization.id if organization else None,
        "name": organization.name if organization else None,
        "address": organization.address_line if organization else None,
        "phone_number": organization.phone_number if organization else None,
    }

    # Add compliance fields ONLY for admins/super_admins
    if current_user.role in ["admin", "super_admin"] and organization:
        org_data["license_number"] = organization.license_number
        org_data["ico_registered"] = organization.ico_registered
        org_data["data_retention_years"] = organization.data_retention_years
        org_data["ico_registration_number"] = organization.ico_registration_number

    # ✅ Add invite code ONLY for admin (not super_admins)
    if current_user.role =="admin" and organization:
        org_data["invite_code"] = organization.invite_code

    return {
        "user_id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "organization": org_data
    }