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
    # ✅ Ensure trip belongs to this driver + org
    trip = db.query(models.Trip).filter(
        models.Trip.id == pod.trip_id,
        models.Trip.driver_id == current_user.id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=403, detail="You are not authorized to create POD for this trip.")

    # ✅ Create POD without trusting user-supplied URLs
    new_pod = models.POD(
        trip_id=pod.trip_id,
        delivered_to=pod.delivered_to,
        signature=pod.signature,
        notes=pod.notes,
        attachment_url="",  # files will be uploaded separately
        driver_id=current_user.id,
        organization_id=current_user.organization_id
    )
    db.add(new_pod)
    db.commit()
    db.refresh(new_pod)

    # ✅ Return clean response (no keys, just metadata, empty list of files)
    return schemas.PODResponse(
        id=new_pod.id,
        trip_id=new_pod.trip_id,
        driver_id=new_pod.driver_id,
        signature=new_pod.signature,
        notes=new_pod.notes,
        delivered_to=new_pod.delivered_to,
        created_at=new_pod.created_at,
        attachment_urls=[]  # nothing uploaded yet
    )

@router.get("/by-trip/{trip_id}", response_model=schemas.PODResponse)
def get_pod_by_trip_id(
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Step 1: Get the POD linked to this trip
    pod = db.query(models.POD).filter(models.POD.trip_id == trip_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="No POD found for this trip")

    # ✅ Step 2: Check organization match
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied — wrong organization")

    # ✅ Step 3: Role-based access
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the driver for this POD")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:
            raise HTTPException(status_code=403, detail="You are not authorized to access this POD")

    # ✅ Step 4: Convert attachment_url keys → presigned URLs
    keys = pod.attachment_url.split(";") if pod.attachment_url else []
    urls = [storage.generate_download_url(k) for k in keys]

    # ✅ Step 5: Return API-friendly schema
    return schemas.PODResponse(
        id=pod.id,
        trip_id=pod.trip_id,
        driver_id=pod.driver_id,
        signature=pod.signature,
        notes=pod.notes,
        delivered_to=pod.delivered_to,
        created_at=pod.created_at,
        file_urls=urls  # ✅ fixed: matches schema
    )
@router.get("/pods/{pod_id}", response_model=schemas.PODResponse)
def get_pod_by_id(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Organization safety
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # 🔒 Role-based access
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the driver for this POD")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:  # ✅ match with schema field
            raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # ✅ Convert stored keys → presigned URLs
    keys = pod.attachment_url.split(";") if pod.attachment_url else []
    urls = [storage.generate_download_url(k) for k in keys]

    # ✅ Return API-friendly schema
    return schemas.PODResponse(
        id=pod.id,
        trip_id=pod.trip_id,
        driver_id=pod.driver_id,
        signature=pod.signature,
        notes=pod.notes,
        delivered_to=pod.delivered_to,
        created_at=pod.created_at,
        file_urls=urls  # ✅ fixed: matches schema
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

    # ✅ Step 5: Store keys (not URLs) in DB
    keys = []
    if raw_key:
        keys.append(raw_key)
    if pdf_key:
        keys.append(pdf_key)
    keys.append(receipt_key)

    new_pod.attachment_url = ";".join(keys)
    db.commit()

    return new_pod


@router.get("/download/{filename}")
def download_pod_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Step 1: Search for a POD in the same org that contains this file
    pod = db.query(models.POD).filter(
        models.POD.organization_id == current_user.organization_id,
        models.POD.attachment_url.contains(filename)  # quicker filter
    ).first()

    if not pod:
        raise HTTPException(status_code=404, detail="File not found")

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

    # ✅ Step 3: Extract the exact file key
    stored_files = pod.attachment_url.split(";") if pod.attachment_url else []
    file_key = next((f for f in stored_files if f.split("/")[-1] == filename), None)

    if not file_key:
        raise HTTPException(status_code=404, detail="File not linked to this POD")

    # ✅ Step 4: Generate presigned download URL (10 mins expiry)
    download_url = storage.generate_download_url(file_key, expires_in=600)

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

    # ✅ Step 3: Generate presigned URLs for all files
    file_keys = pod.attachment_url.split(";") if pod.attachment_url else []
    presigned_urls = [
        storage.generate_download_url(file_key, expires_in=PRESIGNED_EXPIRY)
        for file_key in file_keys
    ]

    return presigned_urls