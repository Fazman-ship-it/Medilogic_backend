from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import shutil, os, uuid
from app.database import get_db
from app.models import DriverCredentials, Document
from app.utilites.logging import log_activity
from app.dependencies import get_current_user
from app import models,schemas
from app.config import settings
from app.models import User, Document, DriverCredentials
from uuid import UUID  
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async, delete_file_from_s3
router = APIRouter(prefix="/drivers", tags=["Driver Credentials"])

@router.post("/{driver_id}/upload-credential")
async def upload_driver_credential(
    driver_id: UUID,
    doc_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    allowed_doc_types = {"license", "adr", "cpc", "dbs", "medical", "training", "insurance", "employment"}
    if doc_type not in allowed_doc_types:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type: {doc_type}")

    credentials = db.query(DriverCredentials).filter_by(user_id=driver_id).first()
    if not credentials:
        raise HTTPException(status_code=404, detail="Driver credentials not found")

    if current_user.organization_id != credentials.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to upload for this driver")

    # ✅ Upload file to S3 (async helper)
    try:
        s3_key = await upload_file_to_s3_async(file, prefix=f"driver_docs/{credentials.organization_id}/{driver_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

    # ✅ Mark old active doc of same type inactive
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == doc_type,
        Document.is_active == True
    ).update({"is_active": False}, synchronize_session="fetch")

    # ✅ Save new document in DB
    document = Document(
        user_id=driver_id,
        organization_id=credentials.organization_id,
        credential_id=credentials.id,
        filename=file.filename,
        file_path=s3_key,  # ✅ store S3 key
        doc_type=doc_type,
        is_active=True
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="upload_driver_credential",
        details=f"{current_user.role} uploaded new {doc_type} for driver {driver_id} (org={credentials.organization_id})"
    )

    # ✅ Generate presigned URL for response
    file_url = await generate_presigned_url_async(s3_key)

    return {
        "message": f"{doc_type} uploaded successfully",
        "document_id": str(document.id),
        "file_url": file_url,
        "is_active": document.is_active
    }
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.database import get_db
from app.models import Document, User
from app.dependencies import get_current_user
from app.schemas import DriverDocumentOut  # Define this schema to include S3 URL

@router.get("/{driver_id}/documents", response_model=List[DriverDocumentOut])
async def list_driver_documents(
    driver_id: UUID,
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    active_only: bool = Query(False, description="Only show active documents"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # --- 1. Ensure driver exists ---
    driver = db.query(User).filter(User.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # --- 2. Multi-tenant restriction ---
    if driver.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # --- 3. Role-based access ---
    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="Drivers can only view their own documents")
    elif current_user.role not in ["driver", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- 4. Build query with optional filters ---
    query = db.query(Document).filter(
        Document.user_id == driver_id,
        Document.organization_id == current_user.organization_id
    )

    if doc_type:
        query = query.filter(Document.doc_type == doc_type)

    if active_only:
        query = query.filter(Document.is_active == True)

    if date_from:
        query = query.filter(Document.upload_time >= date_from)

    if date_to:
        query = query.filter(Document.upload_time <= date_to)

    documents = query.order_by(Document.upload_time.desc()).all()

    # --- 5. Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="list_driver_documents",
        details=f"{current_user.role} listed documents for driver {driver_id}"
    )

    # --- 6. Return documents with presigned S3 URLs ---
    document_out_list = []
    for doc in documents:
        file_url = await generate_presigned_url_async(doc.file_path) if doc.file_path else None
        document_out_list.append(
            DriverDocumentOut(
                id=doc.id,
                filename=doc.filename,
                doc_type=doc.doc_type,
                uploaded_at=doc.upload_time,
                is_active=doc.is_active,
                file_url=file_url
            )
        )

    return document_out_list


    
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.dependencies import require_role
from app.database import get_db
from app.models import Document, User
from app.dependencies import get_current_user  # Assuming you already have RBAC utils
from app.schemas import DocumentOut  # schema for returning documents
from app.schemas import AdminDriverDocumentOut # schema for admin view with driver info


@router.get("/admin/documents", response_model=List[AdminDriverDocumentOut])
async def list_all_driver_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    List all driver documents for the current admin's organization.
    Includes driver name and email alongside each document.
    """

    # --- 1. Get all documents in the admin's organization ---
    documents = (
        db.query(Document)
        .join(User, Document.user_id == User.id)
        .filter(User.organization_id == current_user.organization_id)
        .all()
    )

    # --- 2. Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="list_all_driver_documents",
        details=f"Admin listed all documents for org {current_user.organization_id}"
    )

    # --- 3. Prepare output with S3 presigned URLs ---
    results: List[AdminDriverDocumentOut] = []
    for doc in documents:
        file_url = await generate_presigned_url_async(doc.file_path) if doc.file_path else None
        results.append(
            AdminDriverDocumentOut(
                document_id=doc.id,
                doc_type=doc.doc_type,
                file_url=file_url,
                uploaded_at=doc.upload_time,
                is_active=doc.is_active,
                driver_id=doc.user.id,
                driver_name=doc.user.full_name,
                driver_email=doc.user.email
            )
        )

    return results
from app.schemas import DriverDocumentActivationOut
@router.patch("/drivers/{driver_id}/documents/{document_id}/activate", response_model=DriverDocumentActivationOut)
async def activate_document(
    driver_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Activate a specific document for a driver.
    Only one document per type can be active at a time.
    """
    # --- Fetch driver for multi-tenant validation ---
    driver = db.query(User).filter(
        User.id == driver_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # --- Fetch document ---
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == driver_id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # --- Deactivate other documents of the same type ---
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == document.doc_type,
        Document.id != document.id
    ).update({Document.is_active: False}, synchronize_session=False)

    # --- Activate current document ---
    document.is_active = True
    db.commit()
    db.refresh(document)

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="activate_driver_document",
        details=f"Admin activated document {document.id} for driver {driver_id}"
    )

    # --- Generate presigned S3 URL ---
    file_url = await generate_presigned_url_async(document.file_path) if document.file_path else None

    return {
        "document_id": document.id,
        "doc_type": document.doc_type,
        "is_active": document.is_active,
        "file_url": file_url
    }
from app.utilites.time_utilities import now_utc, to_local, to_utc    
from datetime import datetime, timedelta
from app.schemas import DriverDocumentExpiryResponse
@router.get("/drivers/{driver_id}/documents/expiry-status", response_model=DriverDocumentExpiryResponse)
async def check_document_expiry(
    driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if any driver document is expired or nearing expiry.
    Returns status: valid | expiring_soon | expired
    Includes presigned S3 URL for download.
    """
    # --- 1. Multi-tenant validation ---
    driver = db.query(User).filter(
        User.id == driver_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # --- 2. Role-based access ---
    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="Drivers can only check their own documents")
    elif current_user.role not in ["driver", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- 3. Fetch documents with expiry dates ---
    documents = db.query(Document).filter(
        Document.user_id == driver_id,
        Document.expiry_date.isnot(None)
    ).all()

    now = now_utc()
    warning_period = timedelta(days=30)
    results = []

    for doc in documents:
        if doc.expiry_date < now:
            status = "expired"
        elif doc.expiry_date < now + warning_period:
            status = "expiring_soon"
        else:
            status = "valid"

        file_url = await generate_presigned_url_async(doc.file_path) if doc.file_path else None

        results.append({
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "expiry_date": doc.expiry_date,
            "status": status,
            "days_remaining": max((doc.expiry_date - now).days, 0),
            "file_url": file_url
        })

    # --- 4. Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="check_document_expiry",
        details=f"{current_user.role} checked document expiry for driver {driver_id}"
    )

    return {
        "driver_id": str(driver.id),
        "organization_id": str(driver.organization_id),
        "expiry_status": results
    }
    
# app/routes/driver_credentials.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app import models, schemas, database
from app.dependencies import get_current_user  # JWT user dependency


@router.post("/", response_model=schemas.DriverCredentialsOut)
def create_driver_credentials(
    credentials: schemas.DriverCredentialsCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Multi-tenancy check ---
    if current_user.organization_id != credentials.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # --- Drivers can only create their own credentials ---
    if current_user.role == "driver" and current_user.id != credentials.user_id:
        raise HTTPException(status_code=403, detail="Drivers can only create their own credentials")

    # --- Admin can create for any driver in the same org ---
    if current_user.role == "admin":
        driver = db.query(models.User).filter(
            models.User.id == credentials.user_id,
            models.User.organization_id == current_user.organization_id
        ).first()
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found in your organization")

    # --- Create credential record ---
    db_credentials = models.DriverCredentials(**credentials.dict())
    db.add(db_credentials)
    db.commit()
    db.refresh(db_credentials)

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="create_driver_credentials",
        details=f"{current_user.role} created credentials {db_credentials.id} for driver {db_credentials.user_id} (org={db_credentials.organization_id})"
    )

    # ✅ Note: Documents (files) should be uploaded separately via S3
    return db_credentials

# ✅ Get all driver credentials
from sqlalchemy.orm import joinedload

@router.get("/", response_model=List[schemas.DriverCredentialsOut])
async def get_all_driver_credentials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Fetch credentials based on role with joinedload to avoid N+1 ---
    query = db.query(models.DriverCredentials).options(
        joinedload(models.DriverCredentials.documents)
    ).filter(
        models.DriverCredentials.organization_id == current_user.organization_id
    )

    if current_user.role == "driver":
        query = query.filter(models.DriverCredentials.user_id == current_user.id)
    elif current_user.role not in {"admin", "driver"}:
        raise HTTPException(status_code=403, detail="Not authorized")

    creds = query.all()

    # --- Map credentials to output with S3 URLs for documents ---
    creds_out = []
    for cred in creds:
        doc_urls = []
        for doc in cred.documents:
            if doc.is_active and doc.file_path:
                s3_url = await generate_presigned_url_async(doc.file_path)
                doc_urls.append({
                    "doc_type": doc.doc_type,
                    "url": s3_url,
                    "uploaded_at": doc.upload_time
                })

        creds_out.append({
            "id": cred.id,
            "user_id": cred.user_id,
            "organization_id": cred.organization_id,
            # --- Driving license details ---
            "licence_number": cred.licence_number,
            "licence_category": cred.licence_category,
            "licence_expiry": cred.licence_expiry,
            # --- Regulatory compliance ---
            "adr_certificate": cred.adr_certificate,
            "adr_expiry": cred.adr_expiry,
            "cpc_certificate": cred.cpc_certificate,
            "cpc_expiry": cred.cpc_expiry,
            "dbs_check": cred.dbs_check,
            "dbs_expiry": cred.dbs_expiry,
            "medical_certificate": cred.medical_certificate,
            "medical_expiry": cred.medical_expiry,
            # --- Training certifications ---
            "waste_training_cert": cred.waste_training_cert,
            "infection_control_cert": cred.infection_control_cert,
            "first_aid_cert": cred.first_aid_cert,
            "first_aid_expiry": cred.first_aid_expiry,
            # --- Vehicle insurance ---
            "vehicle_insurance": cred.vehicle_insurance,
            "insurance_expiry": cred.insurance_expiry,
            # --- Employment info ---
            "employment_contract": cred.employment_contract,
            "right_to_work_doc": cred.right_to_work_doc,
            "right_to_work_expiry": cred.right_to_work_expiry,
            # --- Status flags ---
            "is_verified": cred.is_verified,
            "is_active": cred.is_active,
            # --- Associated documents with presigned URLs ---
            "documents": doc_urls
        })

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="list_driver_credentials",
        details=f"{current_user.role} listed {len(creds)} driver credentials (org={current_user.organization_id})"
    )

    return creds_out

from sqlalchemy.orm import joinedload

@router.get("/{credentials_id}", response_model=schemas.DriverCredentialsOut)
async def get_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Fetch credentials with documents in one query ---
    creds = (
        db.query(models.DriverCredentials)
        .options(joinedload(models.DriverCredentials.documents))
        .filter(models.DriverCredentials.id == credentials_id)
        .first()
    )

    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # --- Multi-tenant check ---
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- Role-based access control ---
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only view their own credentials")

    # --- Map documents to presigned URLs ---
    doc_urls = []
    for doc in creds.documents:
        if doc.is_active and doc.attachment_url:  # ✅ use attachment_url instead of file_path
            s3_url = await generate_presigned_url_async(doc.attachment_url)  # ✅ new async helper
            doc_urls.append({
                "doc_type": doc.doc_type,
                "url": s3_url,
                "uploaded_at": doc.upload_time
            })

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="view_driver_credentials",
        details=f"{current_user.role} viewed credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    # --- Return fully mapped output using schema ---
    return schemas.DriverCredentialsOut(
        id=creds.id,
        user_id=creds.user_id,
        organization_id=creds.organization_id,
        licence_number=creds.licence_number,
        licence_category=creds.licence_category,
        licence_expiry=creds.licence_expiry,
        adr_certificate=creds.adr_certificate,
        adr_expiry=creds.adr_expiry,
        cpc_certificate=creds.cpc_certificate,
        cpc_expiry=creds.cpc_expiry,
        dbs_check=creds.dbs_check,
        dbs_expiry=creds.dbs_expiry,
        medical_certificate=creds.medical_certificate,
        medical_expiry=creds.medical_expiry,
        waste_training_cert=creds.waste_training_cert,
        infection_control_cert=creds.infection_control_cert,
        first_aid_cert=creds.first_aid_cert,
        first_aid_expiry=creds.first_aid_expiry,
        vehicle_insurance=creds.vehicle_insurance,
        insurance_expiry=creds.insurance_expiry,
        employment_contract=creds.employment_contract,
        right_to_work_doc=creds.right_to_work_doc,
        right_to_work_expiry=creds.right_to_work_expiry,
        is_verified=creds.is_verified,
        is_active=creds.is_active,
        documents=doc_urls
    )
# ✅ Update driver credentials
from sqlalchemy.orm import joinedload

@router.put("/{credentials_id}", response_model=schemas.DriverCredentialsOut)
async def update_driver_credentials(
    credentials_id: UUID,
    update_data: schemas.DriverCredentialsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Fetch credential with documents ---
    creds = db.query(models.DriverCredentials).options(
        joinedload(models.DriverCredentials.documents)
    ).filter(models.DriverCredentials.id == credentials_id).first()

    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # --- Multi-tenant access check ---
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- Role-based access control ---
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only update their own credentials")

    # --- Apply updates ---
    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(creds, key, value)

    db.commit()
    db.refresh(creds)

    # --- Generate async presigned URLs for associated documents ---
    doc_urls = []
    for doc in creds.documents:
        if doc.is_active and doc.file_path:
            url = await generate_presigned_url_async(doc.file_path)
            doc_urls.append({
                "doc_type": doc.doc_type,
                "url": url,
                "uploaded_at": doc.upload_time
            })

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="update_driver_credentials",
        details=f"{current_user.role} updated credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    # --- Return fully mapped output using schema ---
    return schemas.DriverCredentialsOut(
        id=creds.id,
        user_id=creds.user_id,
        organization_id=creds.organization_id,
        licence_number=creds.licence_number,
        licence_category=creds.licence_category,
        licence_expiry=creds.licence_expiry,
        adr_certificate=creds.adr_certificate,
        adr_expiry=creds.adr_expiry,
        cpc_certificate=creds.cpc_certificate,
        cpc_expiry=creds.cpc_expiry,
        dbs_check=creds.dbs_check,
        dbs_expiry=creds.dbs_expiry,
        medical_certificate=creds.medical_certificate,
        medical_expiry=creds.medical_expiry,
        waste_training_cert=creds.waste_training_cert,
        infection_control_cert=creds.infection_control_cert,
        first_aid_cert=creds.first_aid_cert,
        first_aid_expiry=creds.first_aid_expiry,
        vehicle_insurance=creds.vehicle_insurance,
        insurance_expiry=creds.insurance_expiry,
        employment_contract=creds.employment_contract,
        right_to_work_doc=creds.right_to_work_doc,
        right_to_work_expiry=creds.right_to_work_expiry,
        is_verified=creds.is_verified,
        is_active=creds.is_active,
        documents=doc_urls
    )
# ✅ Delete driver credentials
from sqlalchemy.orm import joinedload
from fastapi import status
@router.delete("/{credentials_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Fetch credentials with documents to avoid N+1 ---
    creds = db.query(models.DriverCredentials).options(
        joinedload(models.DriverCredentials.documents)
    ).filter(models.DriverCredentials.id == credentials_id).first()

    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # --- Multi-tenant access ---
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- Driver role check ---
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only delete their own credentials")

    # --- Delete associated S3 documents ---
    for doc in creds.documents:
        if doc.file_path:
            try:
                await delete_file_from_s3(doc.file_path)  # Async delete from S3
            except Exception as e:
                print(f"❌ Failed to delete {doc.file_path} from S3: {e}")
        db.delete(doc)

    # --- Delete the credential itself ---
    db.delete(creds)
    db.commit()

    # --- Log activity ---
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delete_driver_credentials",
        details=f"{current_user.role} deleted credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    return None