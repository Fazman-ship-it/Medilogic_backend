from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import require_role
from typing import List
from uuid import UUID 
router = APIRouter(
    prefix="/config",
    tags=["System Configuration"]
)

# 🚗 VEHICLE TYPES
@router.post("/vehicle-types/", response_model=schemas.VehicleTypeResponse)
def create_vehicle_type(
    data: schemas.VehicleTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org context
):
    # ✅ Check if vehicle type already exists for this org
    existing = db.query(models.VehicleType).filter_by(
        name=data.name,
        organization_id=current_user.organization_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vehicle type already exists.")

    # ✅ Attach organization_id when creating
    vt = models.VehicleType(
        name=data.name,
        organization_id=current_user.organization_id
    )
    db.add(vt)
    db.commit()
    db.refresh(vt)
    return vt


@router.get("/vehicle-types/", response_model=list[schemas.VehicleTypeResponse])
def list_vehicle_types(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture current org
):
    return db.query(models.VehicleType).filter(
        models.VehicleType.organization_id == current_user.organization_id
    ).all()


@router.delete("/vehicle-types/{vehicle_type_id}")
def delete_vehicle_type(
    vehicle_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    vt = db.query(models.VehicleType).filter_by(
        id=vehicle_type_id,
        organization_id=current_user.organization_id  # ✅ restrict by org
    ).first()

    if not vt:
        raise HTTPException(status_code=404, detail="Vehicle type not found.")

    db.delete(vt)
    db.commit()
    return {"detail": "Vehicle type deleted successfully."}

# Inside app/routes/system_config.py (continue after VehicleType)

@router.post("/priority-levels", response_model=schemas.PriorityLevelResponse)
def create_priority_level(data: schemas.PriorityLevelCreate, db: Session = Depends(get_db), _: models.User = Depends(require_role("admin"))):
    level = models.PriorityLevel(name=data.name)
    db.add(level)
    db.commit()
    db.refresh(level)
    return level

@router.get("/priority-levels", response_model=List[schemas.PriorityLevelResponse])
def get_priority_levels(db: Session = Depends(get_db), _: models.User = Depends(require_role("admin"))):
    return db.query(models.PriorityLevel).all()

@router.delete("/priority-levels/{level_id}")
def delete_priority_level(level_id: UUID, db: Session = Depends(get_db), _: models.User = Depends(require_role("admin"))):
    level = db.query(models.PriorityLevel).get(level_id)
    if not level:
        raise HTTPException(status_code=404, detail="Priority level not found")
    db.delete(level)
    db.commit()
    return {"detail": "Priority level deleted"}


# ✅ SHIFT WINDOWS

@router.post("/shift-windows", response_model=schemas.ShiftWindowResponse)
def create_shift_window(
    data: schemas.ShiftWindowCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    shift = models.ShiftWindow(
        name=data.name,
        organization_id=current_user.organization_id  # ✅ associate with org
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift

@router.get("/shift-windows", response_model=list[schemas.ShiftWindowResponse])
def get_shift_windows(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    return db.query(models.ShiftWindow).filter(
        models.ShiftWindow.organization_id == current_user.organization_id
    ).all()


@router.delete("/shift-windows/{shift_id}")
def delete_shift_window(
    shift_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    shift = db.query(models.ShiftWindow).filter_by(
        id=shift_id,
        organization_id=current_user.organization_id  # ✅ enforce org scoping
    ).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift window not found")

    db.delete(shift)
    db.commit()
    return {"detail": "Shift window deleted"}

# ZONES

@router.post("/zones", response_model=schemas.ZoneResponse)
def create_zone(
    data: schemas.ZoneCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    zone = models.Zone(
        name=data.name,
        organization_id=current_user.organization_id  # ✅ scope to org
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.get("/zones", response_model=list[schemas.ZoneResponse])
def get_zones(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    return db.query(models.Zone).filter(
        models.Zone.organization_id == current_user.organization_id
    ).all()

@router.delete("/zones/{zone_id}")
def delete_zone(
    zone_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture org
):
    zone = db.query(models.Zone).filter_by(
        id=zone_id,
        organization_id=current_user.organization_id  # ✅ scoped deletion
    ).first()

    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    db.delete(zone)
    db.commit()
    return {"detail": "Zone deleted"}