from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_role,get_current_user
from app.auth import get_password_hash, verify_password
from app.utilites.logging import log_activity
from app import models, schemas
from app.utilites.generator import generate_invite_code
from app.models import User
from typing import List
from app.schemas import UserOut, OrganizationCreate, OrganizationOut
from app.models import Organization
from app.utilites.user_onboarding import send_welcome_email
from uuid import UUID
router = APIRouter(prefix="/super", tags=["Super Admin"])


@router.post("/create-user", status_code=201)
def create_user_by_super_admin(
    data: schemas.SuperAdminCreateUser,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    # Check if email already exists
    if db.query(models.User).filter_by(email=data.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")

    # Check if organization exists
    org = db.query(models.Organization).filter_by(id=data.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # ✅ Prevent multiple admins per organization
    if data.role == "admin":
        existing_admin = db.query(models.User).filter_by(
            organization_id=org.id, role="admin"
        ).first()
        if existing_admin:
            raise HTTPException(
                status_code=400,
                detail=f"Organization {org.name} already has an admin assigned."
            )

    # Create user
    hashed_pw = get_password_hash(data.password)
    new_user = models.User(
        name=data.name,
        email=data.email,
        hashed_password=hashed_pw,
        role=data.role,
        organization_id=org.id,
        is_verified=True,
        email_verification_token=None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action=f"Created {data.role} '{data.email}' for organization {org.name}"
    )

    # ✅ Send welcome email to the new user
    send_welcome_email(
        to_email=data.email,
        full_name=data.name,
        role=data.role,
        organization_id=str(org.id),
        invite_code=org.invite_code,
        temp_password=data.password,
        login_link="https://medilogic.vercel.app/login"
    )

    return {
        "message": f"{data.role.capitalize()} user created successfully",
        "user_id": new_user.id
    }

 

from sqlalchemy import func
@router.get("/organizations", response_model=list[schemas.OrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    orgs_with_counts = (
        db.query(
            models.Organization,
            func.count(models.User.id).label("user_count")
        )
        .outerjoin(models.User, models.User.organization_id == models.Organization.id)
        .group_by(models.Organization.id)
        .all()
    )

    result = []
    for org, user_count in orgs_with_counts:
        org_out = schemas.OrganizationOut.from_orm(org)
        org_out.user_count = user_count
        result.append(org_out)

    return result

@router.post("/organizations", response_model=schemas.OrganizationOut)
def create_organization(
    org_data: schemas.OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    # Check for duplicate org name (optional)
    if db.query(models.Organization).filter_by(name=org_data.name).first():
        raise HTTPException(status_code=400, detail="Organization name already exists")

    invite_code = generate_invite_code()

    new_org = models.Organization(
        name=org_data.name,
        type=org_data.type,
        country=org_data.country,
        state=org_data.state,
        region=org_data.region,
        invite_code=invite_code,
        ico_registered=org_data.ico_registered,
        data_retention_years=org_data.data_retention_years,
        is_active=True
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="create_organization",
        details=f"Super admin created organization '{new_org.name}' with code {new_org.invite_code}"
    )

    return new_org


@router.delete("/{org_id}")
def deactivate_organization(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if not org.is_active:
        raise HTTPException(status_code=400, detail="Organization already deactivated")

    # ✅ Soft deactivate instead of delete
    org.is_active = False
    db.commit()

    # ✅ Optionally deactivate all users in this org
    users = db.query(models.User).filter(models.User.organization_id == org_id).all()
    for user in users:
        user.is_active = False  # (Assumes your User model has is_active)
    db.commit()

    # ✅ Log the action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="deactivate_organization",
        details=f"Super admin {current_user.email} deactivated organization {org.name} (ID {org.id})"
    )

    return {"message": f"Organization '{org.name}' has been deactivated."}

@router.patch("/{org_id}")
def update_organization(
    org_id: UUID,
    update: schemas.OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Multi-tenant check for org admins
    if current_user.role == "admin":
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this organization")

    # Role-based restrictions
    restricted_fields = {"is_active", "invite_code"}
    for field, value in update.dict(exclude_unset=True).items():
        if current_user.role == "admin" and field in restricted_fields:
            continue  # skip restricted fields for org admins
        setattr(org, field, value)

    db.commit()
    db.refresh(org)

    # Activity log
    action_type = "update_organization" if current_user.role == "super_admin" else "update_own_organization"
    log_activity(
        db=db,
        user_id=current_user.id,
        action=action_type,
        details=f"{current_user.role.capitalize()} updated organization {org.name} (ID: {org.id})"
    )

    return {"message": "Organization updated successfully", "organization": org}

@router.get("/{org_id}")
def get_organization_details(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    org = db.query(models.Organization).filter_by(id=org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    users = db.query(models.User).filter_by(organization_id=org.id).all()
    trip_count = db.query(models.Trip).filter_by(organization_id=org.id).count()

    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "invite_code": org.invite_code,
            "is_active": org.is_active,
            "email": org.email,
            "phone_number": org.phone_number,
            "address_line": org.address_line,
            "postal_code": org.postal_code,
            "license_number": org.license_number,
            "ico_registered": org.ico_registered,
            "data_retention_years": org.data_retention_years,
            "license_expiry": org.license_expiry,
            "supported_waste_types": org.supported_waste_types
        },
        "user_count": len(users),
        "trip_count": trip_count,
    }
    
    
@router.post("/{org_id}/regenerate-code")
def regenerate_invite_code(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    from app.utilites.generator import generate_invite_code

    org = db.query(models.Organization).filter_by(id=org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.invite_code = generate_invite_code()
    db.commit()

    log_activity(
        db=db,
        user_id=current_user.id,
        action="regenerate_invite_code",
        details=f"Super admin regenerated invite code for organization {org.name} (ID: {org.id})"
    )

    return {"message": "Invite code regenerated", "new_invite_code": org.invite_code}    

@router.get("/super/orgs/{org_id}/users")
def get_org_users(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    users = db.query(models.User).filter(models.User.organization_id == org_id).all()
    return users


@router.post("/super/regulators", response_model=schemas.UserOut)
def create_regulator(
    regulator: schemas.RegulatorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    # 🚫 Check if regulator already exists
    existing = db.query(User).filter(User.email == regulator.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    # ✅ Hash the password
    hashed_password = get_password_hash(regulator.password)

    # ✅ Create the regulator user
    new_user = User(
        email=regulator.email,
        name=regulator.name,
        hashed_password=hashed_password,
        role="regulator",
        regulated_country=regulator.regulated_country,
        regulated_state=regulator.regulated_state,
        regulated_region=regulator.regulated_region
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ✅ Send welcome email
    send_welcome_email(
        to_email=regulator.email,
        full_name=regulator.name,
        role="regulator",
        temp_password=regulator.password,
        login_link="https://medilogic.vercel.app/login"
    )

    return new_user

@router.get("/super/regulators", response_model=List[schemas.RegulatorOut])
def list_regulators(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    return db.query(User).filter(User.role == "regulator").all()


@router.delete("/organizations/{org_id}/permanent", status_code=204)
def delete_organization_permanently(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    db.delete(org)
    db.commit()
    return {"message": "Organization permanently deleted."}

@router.patch("/{org_id}/activate")
def activate_organization(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if org.is_active:
        raise HTTPException(status_code=400, detail="Organization is already active")

    # ✅ Reactivate the organization
    org.is_active = True
    db.commit()

    # ✅ Optionally reactivate all users in this org
    users = db.query(models.User).filter(models.User.organization_id == org_id).all()
    for user in users:
        user.is_active = True  # (Assumes your User model has is_active)
    db.commit()

    # ✅ Log the action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="activate_organization",
        details=f"Super admin {current_user.email} reactivated organization {org.name} (ID {org.id})"
    )

    return {"message": f"Organization '{org.name}' has been reactivated."}

# ✅ Activate a regulator (super admin only)
@router.patch("/super/regulators/{regulator_id}/activate", response_model=schemas.UserOut)
def activate_regulator(
    regulator_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    regulator = db.query(User).filter(User.id == regulator_id, User.role == "regulator").first()
    if not regulator:
        raise HTTPException(status_code=404, detail="Regulator not found")

    if regulator.is_active:
        raise HTTPException(status_code=400, detail="Regulator already active")

    regulator.is_active = True
    db.commit()
    db.refresh(regulator)

    return regulator

# 🚫 Deactivate a regulator (super_admin only)
@router.put("/super/regulators/{regulator_id}/deactivate", response_model=schemas.UserOut)
def deactivate_regulator(
    regulator_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    regulator = db.query(User).filter(User.id == regulator_id, User.role == "regulator").first()
    if not regulator:
        raise HTTPException(status_code=404, detail="Regulator not found")

    if not regulator.is_active:
        raise HTTPException(status_code=400, detail="Regulator is already deactivated")

    regulator.is_active = False
    db.commit()
    db.refresh(regulator)

    return regulator

# ❌ Permanently delete a regulator (super_admin only)
@router.delete("/super/regulators/{regulator_id}", response_model=dict)
def delete_regulator(
    regulator_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    regulator = db.query(User).filter(User.id == regulator_id, User.role == "regulator").first()
    if not regulator:
        raise HTTPException(status_code=404, detail="Regulator not found")

    db.delete(regulator)
    db.commit()

    return {"detail": f"Regulator with ID {regulator_id} has been permanently deleted."}


# ✅ Activate an admin/user (super_admin only)
@router.patch("/super/users/{user_id}/activate", response_model=dict)
def activate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    # ✅ Activate the user
    user.is_active = True
    db.commit()
    db.refresh(user)

    # ✅ Log the action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="activate_user",
        details=f"Super Admin {current_user.email} activated user {user.email} (ID: {user.id})"
    )

    return {"detail": f"User {user.email} has been activated."}

# ✅ Deactivate an admin/user (super_admin only)
@router.patch("/super/users/{user_id}/deactivate", response_model=dict)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is already deactivated")

    # ✅ Deactivate the user
    user.is_active = False
    db.commit()
    db.refresh(user)

    # ✅ Log the action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="deactivate_user",
        details=f"Super Admin {current_user.email} deactivated user {user.email} (ID: {user.id})"
    )

    return {"detail": f"User {user.email} has been deactivated."}

# ✅ Permanently delete an admin/user (super_admin only)
@router.delete("/super/users/{user_id}", response_model=dict)
def delete_user_permanently(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin"))
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🚫 Prevent super_admins from deleting themselves
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Super Admin cannot delete themselves")

    # ✅ Delete the user
    db.delete(user)
    db.commit()

    # ✅ Log the action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delete_user_permanently",
        details=f"Super Admin {current_user.email} permanently deleted user {user.email} (ID: {user.id})"
    )

    return {"detail": f"User {user.email} has been permanently deleted."}

@router.get("/{org_id}/invite-code")
def get_invite_code(
    org_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    # Check if the admin belongs to this org
    if current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this organization’s invite code")

    org = db.query(models.Organization).filter_by(id=org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {"invite_code": org.invite_code}

@router.put("/regulator/profile", response_model=schemas.RegulatorOut)
def update_regulator_profile(
    update: schemas.RegulatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("regulator"))
):
    regulator = db.query(User).filter(User.id == current_user.id).first()
    if not regulator:
        raise HTTPException(status_code=404, detail="Regulator not found")

    # Regulators can update only their own compliance/contact details
    regulator.organization_name = update.organization_name
    regulator.license_number = update.license_number
    regulator.license_expiry = update.license_expiry
    regulator.phone_number = update.phone_number
    regulator.address = update.address
    regulator.regulated_waste_types = update.regulated_waste_types
    regulator.email = update.email
    regulator.name = update.name
    regulator.regulated_goods_types = update.regulated_goods_types
    regulator.regulated_logistics_scope = update.regulated_logistics_scope

    # 🚫 Prevent regulators from changing jurisdiction
    # regulator.regulated_country = update.regulated_country
    # regulator.regulated_state = update.regulated_state
    # regulator.regulated_region = update.regulated_region

    db.commit()
    db.refresh(regulator)
    return regulator

@router.patch("/super/regulator/{regulator_id}/jurisdiction", response_model=schemas.RegulatorOut)
def update_regulator_jurisdiction(
    regulator_id: UUID,
    update: schemas.RegulatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    regulator = db.query(User).filter(User.id == regulator_id).first()
    if not regulator or regulator.role != "regulator":
        raise HTTPException(status_code=404, detail="Regulator not found")

    # ✅ Only update fields that were provided
    if update.regulated_country is not None:
        regulator.regulated_country = update.regulated_country
    if update.regulated_state is not None:
        regulator.regulated_state = update.regulated_state
    if update.regulated_region is not None:
        regulator.regulated_region = update.regulated_region

    db.commit()
    db.refresh(regulator)
    return regulator


@router.get("/admin/regulators/{regulator_id}", response_model=schemas.RegulatorOut)
def get_regulator_by_id(
    regulator_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    regulator = db.query(User).filter(User.id == regulator_id, User.role == "regulator").first()
    if not regulator:
        raise HTTPException(status_code=404, detail="Regulator not found")
    return regulator