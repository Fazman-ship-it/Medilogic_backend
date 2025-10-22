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
async def get_pod_by_id(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Organization & role checks
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the driver for this POD")
    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.full_name:
            raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # ✅ Fetch related files + generate URLs
    pod_files = db.query(models.PODFile).filter(models.PODFile.pod_id == pod.id).all()
    file_objects = []
    for f in pod_files:
        if f.s3_key:
            url = await generate_presigned_url_async(f.s3_key)
            file_objects.append({
                "id": str(f.id),
                "s3_key": f.s3_key,
                "file_type": f.file_type,
                "url": url
            })

    # ✅ Return schema-compliant structure
    return schemas.PODResponse(
        id=pod.id,
        trip_id=pod.trip_id,
        driver_id=pod.driver_id,
        signature=pod.signature,
        notes=pod.notes,
        delivered_to=pod.delivered_to,
        created_at=pod.created_at,
        files=file_objects   # 🔥 correct field name!
    )
# app/routes/pods.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
import uuid
import os
from app import models, schemas
from app.database import get_db
from app.dependencies import require_role, get_current_user
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async

@router.post("/upload", response_model=schemas.PODResponse)
async def create_pod_with_files(
    trip_id: UUID = Form(...),
    delivered_to: str = Form(...),
    notes: Optional[str] = Form(None),
    signature: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),  # ✅ Multiple file uploads
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

    # ✅ Step 2: Create the POD record first
    new_pod = models.POD(
        trip_id=trip_id,
        delivered_to=delivered_to,
        signature=signature,
        notes=notes,
        driver_id=current_user.id,
        organization_id=current_user.organization_id
    )
    db.add(new_pod)
    db.commit()
    db.refresh(new_pod)

    # ✅ Step 3: Handle multiple file uploads (images + PDFs)
    uploaded_files = []
    if files:
        for file in files:
            if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")

            uploaded_key = await upload_file_to_s3_async(file, prefix="uploads")

            file_type = (
                "pdf" if file.content_type == "application/pdf"
                else "raw"
            )

            db.add(models.PODFile(pod_id=new_pod.id, s3_key=uploaded_key, file_type=file_type))
            uploaded_files.append(uploaded_key)

    db.commit()

    # ✅ Step 4: Generate & upload ONE receipt PDF for all uploaded files
    receipt_filename = f"{new_pod.id}_receipt.pdf"
    receipt_path = f"/tmp/{receipt_filename}"

    generate_pod_pdf(new_pod, receipt_path)  # same as before

    with open(receipt_path, "rb") as pdf_file:
        uploaded_receipt_key = await upload_file_to_s3_async(
            file=pdf_file,
            prefix="receipts",
            filename=receipt_filename,
            content_type="application/pdf"
        )

    # ✅ Step 5: Save the receipt file record
    db.add(models.PODFile(pod_id=new_pod.id, s3_key=uploaded_receipt_key, file_type="receipt"))
    db.commit()
    db.refresh(new_pod)

    # ✅ Clean up temporary file
    if os.path.exists(receipt_path):
        os.remove(receipt_path)

    return new_pod
    
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
import aioboto3
from app import models
from app.dependencies import get_db, get_current_user
from app.config import settings 

@router.get("/download/{filename}")
async def download_pod_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Step 1: Find the PODFile record by filename and org
    pod_file = (
        db.query(models.PODFile)
        .join(models.POD)
        .filter(
            models.POD.organization_id == current_user.organization_id,
            models.PODFile.s3_key.like(f"%{filename}")
        )
        .first()
    )

    if not pod_file:
        raise HTTPException(status_code=404, detail="File not found")

    pod = pod_file.pod

    # ✅ Step 2: Role-based access
    if current_user.role == "driver" and pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don’t have access to this POD file")

    if current_user.role == "client":
        trip = db.query(models.Trip).filter(
            models.Trip.id == pod.trip_id,
            models.Trip.organization_id == current_user.organization_id
        ).first()
        if not trip or trip.client_name != current_user.name:
            raise HTTPException(status_code=403, detail="You don’t have access to this POD file")

    # ✅ Step 3: Stream file directly from S3
    key = pod_file.s3_key
    download_name = key.split("/")[-1]

    session = aioboto3.Session()
    try:
        async with session.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        ) as s3:
            s3_object = await s3.get_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
            file_stream = s3_object["Body"]
            content_type = s3_object.get("ContentType", "application/octet-stream")

            return StreamingResponse(
                file_stream,
                media_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="{download_name}"'}
            )

    except ClientError as e:
        raise HTTPException(status_code=404, detail=f"S3 error: {str(e)}")
        
from app.config import settings
@router.get("/{pod_id}/files", response_model=List[schemas.PODFileOut])
async def list_pod_files(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Return all files for a specific POD, with type and URL."""
    
    # ✅ Step 1: Fetch POD
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Step 2: Access control
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
    response_files = []
    for pf in pod_files:
        url = await generate_presigned_url_async(pf.s3_key, expires_in=settings.PRESIGNED_EXPIRY)
        response_files.append({
            "id": str(pf.id),
            "file_type": pf.file_type,
            "s3_key": pf.s3_key,
            "url": url
        })

    # ✅ Step 5: Return full file info
    return response_files
    
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async

@router.get("/", response_model=List[schemas.PODResponse])
async def list_all_pods(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    driver_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ✅ Retrieve all PODs in the organization.
    - Drivers: see only their own PODs.
    - Admins/Managers: see all PODs in their organization.
    - Optional filters: date range, driver_id.
    """
    query = db.query(models.POD).filter(
        models.POD.organization_id == current_user.organization_id
    )

    # Restrict to driver’s own PODs if driver
    if current_user.role == "driver":
        query = query.filter(models.POD.driver_id == current_user.id)
    elif driver_id:
        query = query.filter(models.POD.driver_id == driver_id)

    # Optional date filters
    if start_date:
        query = query.filter(models.POD.created_at >= start_date)
    if end_date:
        query = query.filter(models.POD.created_at <= end_date)

    pods = query.order_by(models.POD.created_at.desc()).all()

    results = []
    for pod in pods:
        files_data = []
        if pod.files:
            for f in pod.files:
                try:
                    url = await generate_presigned_url_async(f.s3_key, expires_in=600)
                    files_data.append({
                        "id": f.id,
                        "file_type": f.file_type,
                        "s3_key": f.s3_key,
                        "url": url
                    })
                except Exception:
                    continue

        results.append({
            "id": pod.id,
            "trip_id": pod.trip_id,
            "driver_id": pod.driver_id,
            "signature": pod.signature,
            "notes": pod.notes,
            "delivered_to": pod.delivered_to,
            "created_at": pod.created_at,
            "files": files_data
        })

    return results

from fastapi import status
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async, delete_file_from_s3

@router.delete("/pods/{pod_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pod(
    pod_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Delete a POD and all associated files (both DB + S3)
    Only the driver who created the POD can delete it.
    """
    # ✅ Step 1: Fetch POD
    pod = db.query(models.POD).filter(models.POD.id == pod_id).first()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")

    # ✅ Step 2: Ensure user belongs to same organization
    if pod.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this POD")

    # ✅ Step 3: Allow only the driver who created the POD
    if current_user.role != "driver" or pod.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the driver who created this POD can delete it")

    # ✅ Step 4: Fetch related files
    pod_files = db.query(models.PODFile).filter(models.PODFile.pod_id == pod.id).all()

    # ✅ Step 5: Delete files from S3 (async)
    for f in pod_files:
        try:
            await delete_file_from_s3(f.s3_key)
        except Exception as e:
            print(f"⚠️ Failed to delete S3 file {f.s3_key}: {e}")

    # ✅ Step 6: Delete the POD (cascade removes its files)
    db.delete(pod)
    db.commit()

    return {"detail": "POD and all files deleted successfully"}