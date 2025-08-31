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
from app.utilites.raw_convert import ensure_pdf


router = APIRouter(prefix="/pods", tags=["PODs"])

@router.post("/", response_model=schemas.PODResponse)
def create_pod(
    pod: schemas.PODCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("driver"))  # ✅ Only drivers
):
    # ✅ Fetch trip and ensure driver ownership and organization match
    trip = db.query(models.Trip).filter(
        models.Trip.id == pod.trip_id,
        models.Trip.driver_id == current_user.id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=403, detail="You are not authorized to create POD for this trip.")

    # ✅ Create POD and attach org from driver
    new_pod = models.POD(
        trip_id=pod.trip_id,
        delivered_to=pod.delivered_to,
        signature=pod.signature,
        notes=pod.notes,
        attachment_url=pod.attachment_url,
        driver_id=current_user.id,
        organization_id=current_user.organization_id  # ✅ Inject org_id securely
    )
    db.add(new_pod)
    db.commit()
    db.refresh(new_pod)
    return new_pod


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
    if current_user.role == "admin":
        return pod

    elif current_user.role == "driver":
        if pod.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="You are not the driver for this POD")
        return pod

    elif current_user.role == "client":
        # Double-check the trip's client name matches current user
        trip = db.query(models.Trip).filter(
            models.Trip.id == trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()

        if not trip or trip.client_name != current_user.full_name:
            raise HTTPException(status_code=403, detail="You are not authorized to access this POD")
        return pod

    raise HTTPException(status_code=403, detail="Access denied")

@router.get("/pods/{pod_id}", response_model=schemas.PODResponse)
def get_pod_by_id(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pod = db.query(POD).filter(POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Check organization match first
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # 🔒 Role-based access
    if current_user.role == "admin":
        return pod
    elif current_user.role == "driver" and pod.driver_id == current_user.id:
        return pod
    elif current_user.role == "client":
        # ✅ Check if this client is related to the trip AND same org
        trip = db.query(Trip).filter(
            Trip.id == pod.trip_id,
            Trip.organization_id == current_user.organization_id
        ).first()
        if trip and trip.client_name == current_user.name:
            return pod

    raise HTTPException(status_code=403, detail="You don't have access to this POD")

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
    # ✅ Step 1: Validate trip belongs to this driver & org
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.driver_id == current_user.id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=403, detail="You are not authorized to create POD for this trip.")

    # ✅ Step 2: Validate and save uploaded file (optional)
    raw_url = None
    pdf_url = None
    if file:
        if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"

        # Save raw file inside /uploads/pods/raw/
        raw_path = os.path.join("app", "uploads", "pods", "raw", filename)
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        with open(raw_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        raw_url = f"/uploads/pods/raw/{filename}"

        # ✅ If it's an image, auto-convert to PDF
        if file.content_type in ["image/jpeg", "image/png"]:
            from app.utilites.raw_convert import ensure_pdf_exists
            pdf_filename = ensure_pdf_exists(filename)  # will save into /pdf/
            if pdf_filename:
                pdf_url = f"/uploads/pods/pdf/{pdf_filename}"
        else:
            # already a PDF
            pdf_url = raw_url

    # ✅ Step 3: Save POD to DB (initially only uploaded file if exists)
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

    # ✅ Step 4: Generate PDF receipt
    receipt_filename = f"{new_pod.id}_receipt.pdf"
    generate_pod_pdf(new_pod, receipt_filename)
    receipt_url = f"/pods/files/{receipt_filename}"

    # ✅ Step 5: Update attachment_url to include raw + pdf + receipt
    urls = []
    if raw_url:
        urls.append(raw_url)
    if pdf_url:
        urls.append(pdf_url)
    urls.append(receipt_url)

    new_pod.attachment_url = ";".join(urls)
    db.commit()

    return new_pod
    

from fastapi.responses import FileResponse
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.raw_convert import ensure_pdf_exists
# Directories
UPLOAD_DIR_RAW = "app/static/uploads/pods/raw/"
UPLOAD_DIR_PDF = "app/static/uploads/pods/pdf/"

@router.get("/download/{filename}")
def download_pod_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Step 1: Look up the POD by filename
    pods = db.query(models.POD).filter(
        models.POD.organization_id == current_user.organization_id
    ).filter(
        models.POD.attachment_url.isnot(None)
    ).all()

    pod = next(
        (p for p in pods if filename in [f.split("/")[-1] for f in p.attachment_url.split(";")]),
        None
    )

    if not pod:
        raise HTTPException(status_code=404, detail="File not found")

    stored_files = pod.attachment_url.split(";") if pod.attachment_url else []
    file_url = next((f for f in stored_files if f.split("/")[-1] == filename), None)

    if not file_url:
        raise HTTPException(status_code=404, detail="File not linked to this POD")

    # Step 2: Determine folder based on role
    safe_filename = os.path.basename(file_url)  # prevents path traversal

    if current_user.role == "admin":
        # Admins try raw first, then PDF fallback
        file_path = os.path.join(UPLOAD_DIR_RAW, safe_filename)
        if not os.path.exists(file_path):
            # fallback to PDF
            pdf_filename = ensure_pdf_exists(safe_filename)
            if not pdf_filename:
                raise HTTPException(status_code=404, detail="File not found")
            file_path = os.path.join(UPLOAD_DIR_PDF, pdf_filename)
    else:
        # Clients/Drivers can only download PDF
        pdf_filename = ensure_pdf_exists(safe_filename)
        if not pdf_filename:
            raise HTTPException(status_code=404, detail="PDF not found")
        file_path = os.path.join(UPLOAD_DIR_PDF, pdf_filename)

    # Step 3: Ensure file exists
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    # Step 4: Return file response
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path)
    )

@router.get("/{pod_id}/files", response_model=List[str])
def list_pod_files(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Step 1: Fetch the POD
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Step 2: Organization safety check
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied — wrong organization")

    # ✅ Step 3: Role-based access control (same logic as file download)
    if current_user.role == "admin":
        pass
    elif current_user.role == "driver":
        if pod.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="You don't have access to this POD")
    elif current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:
            raise HTTPException(status_code=403, detail="You don't have access to this POD")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Step 4: Return list of attached files (split if multiple)
    files = pod.attachment_url.split(";") if pod.attachment_url else []
    return files