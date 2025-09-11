# app/routes/pod.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db
from app.dependencies import require_role
from fastapi import Form, File, UploadFile
import shutil
import os
from typing import Optional
from app.utilites.pdf_generator import generate_pod_pdf
from app.dependencies import get_current_user
from app.models import POD, User, Trip
from uuid import UUID

router = APIRouter(prefix="/pods", tags=["PODs"])

@router.post("/", response_model=schemas.PODResponse)
def create_pod(
    pod: schemas.PODCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("driver"))  # ✅ Only drivers
):
    # ✅ Step 1: Ensure trip belongs to this driver + org
    trip = db.query(models.Trip).filter(
        models.Trip.id == pod.trip_id,
        models.Trip.driver_id == current_user.id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=403, detail="You are not authorized to create POD for this trip.")

    # ✅ Step 2: Create POD (no files yet, no attachment_url)
    new_pod = models.POD(
        trip_id=pod.trip_id,
        delivered_to=pod.delivered_to,
        signature=pod.signature,
        notes=pod.notes,
        driver_id=current_user.id,
        organization_id=current_user.organization_id
    )
    db.add(new_pod)
    db.commit()
    db.refresh(new_pod)

    # ✅ Step 3: Return schema response (empty files list for now)
    return schemas.PODResponse(
        id=new_pod.id,
        trip_id=new_pod.trip_id,
        driver_id=new_pod.driver_id,
        signature=new_pod.signature,
        notes=new_pod.notes,
        delivered_to=new_pod.delivered_to,
        created_at=new_pod.created_at,
        file_urls=[]  # ✅ fixed: no attachment_url anymore
    )

@router.get("/pods/{pod_id}", response_model=schemas.PODResponse)
def get_pod_by_id(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Step 1: Fetch POD
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Step 2: Multi-tenant org check
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # ✅ Step 3: Role-based access
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the driver for this POD")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:  
            raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # ✅ Step 4: Fetch related files
    pod_files = db.query(models.PODFile).filter(models.PODFile.pod_id == pod.id).all()
    urls = [
        storage.generate_download_url(f.s3_key)
        for f in pod_files
    ]

    # ✅ Step 5: Return schema-friendly response
    return schemas.PODResponse(
        id=pod.id,
        trip_id=pod.trip_id,
        driver_id=pod.driver_id,
        signature=pod.signature,
        notes=pod.notes,
        delivered_to=pod.delivered_to,
        created_at=pod.created_at,
        file_urls=urls
    )

# app/routes/pods.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
import uuid
from app import models, schemas
from app.database import get_db
from app.dependencies import require_role, get_current_user
from app.storage import S3Storage

storage = S3Storage()

@router.post("/upload", response_model=schemas.PODResponse)
def create_pod_with_file(
    trip_id: UUID = Form(...),
    delivered_to: str = Form(...),
    notes: Optional[str] = Form(None),
    signature: Optional[str] = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("driver"))
):
    # ✅ Step 1: Validate trip belongs to driver & org
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.driver_id == current_user.id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=403, detail="You are not authorized for this trip.")

    # ✅ Step 2: Upload file to S3
    raw_key = None
    pdf_key = None
    if file:
        if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        raw_key, pdf_key = storage.save_file(file)

    # ✅ Step 3: Save POD to DB (keys only, no URLs)
    new_pod = models.POD(
        trip_id=trip_id,
        delivered_to=delivered_to,
        signature=signature,
        notes=notes,
        attachment_url="",  # will update below
        driver_id=current_user.id,
        organization_id=current_user.organization_id
    )
    db.add(new_pod)
    db.commit()
    db.refresh(new_pod)

    # ✅ Step 4: Generate PDF receipt and upload to S3
    receipt_filename = f"{new_pod.id}_receipt.pdf"
    generate_pod_pdf(new_pod, receipt_filename)

    receipt_key = f"pods/receipts/{receipt_filename}"
    with open(receipt_filename, "rb") as pdf_file:
        storage.client.upload_fileobj(pdf_file, storage.bucket, receipt_key)

    # ✅ Step 5: Store files in DB (separately, not as string)
    if raw_key:
        db.add(models.PODFile(pod_id=new_pod.id, s3_key=raw_key, file_type="raw"))

    if pdf_key:
        db.add(models.PODFile(pod_id=new_pod.id, s3_key=pdf_key, file_type="pdf"))

    db.add(models.PODFile(pod_id=new_pod.id, s3_key=receipt_key, file_type="receipt"))

    db.commit()
    db.refresh(new_pod)

    return new_pod

@router.get("/download/{filename}")
def download_pod_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Step 1: Find the PODFile by filename and org
    pod_file = (
        db.query(models.PODFile)
        .join(models.POD)
        .filter(
            models.POD.organization_id == current_user.organization_id,
            models.PODFile.s3_key.like(f"%{filename}")  # match by file name
        )
        .first()
    )

    if not pod_file:
        raise HTTPException(status_code=404, detail="File not found")

    pod = pod_file.pod  # thanks to relationship

    # ✅ Step 2: Verify role-based access
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don’t have access to this POD file")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.name:
            raise HTTPException(status_code=403, detail="You don’t have access to this POD file")

    # ✅ Step 3: Generate presigned download URL (10 mins expiry)
    download_url = storage.generate_download_url(pod_file.s3_key, expires_in=600)

    return {"download_url": download_url}

from app.config import settings
PRESIGNED_EXPIRY = 600  # 10 minutes, can move to settings.py later
@router.get("/{pod_id}/files", response_model=List[str])
def list_pod_files(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Step 1: Fetch POD
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Step 2: Org & role access control
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:
            raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Step 3: Fetch all related PODFiles
    pod_files = db.query(models.PODFile).filter(models.PODFile.pod_id == pod.id).all()

    if not pod_files:
        return []

    # ✅ Step 4: Generate presigned URLs for each file
    presigned_urls = [
        storage.generate_download_url(pf.s3_key, expires_in=PRESIGNED_EXPIRY)
        for pf in pod_files
    ]

    return presigned_urls