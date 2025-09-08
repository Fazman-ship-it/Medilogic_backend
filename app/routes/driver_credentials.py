from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import shutil, os, uuid
from app.database import get_db
from app.models import DriverCredentials, Document
from app.utilites.logging import log_activity
from app.dependencies import get_current_user
from app import models,schemas
from app.storage import S3Storage
from app.config import settings
storage = S3Storage()
router = APIRouter(prefix="/drivers", tags=["Driver Credentials"])

@router.post("/{driver_id}/upload-credential")
async def upload_driver_credential(
    driver_id: uuid.UUID,
    doc_type: str,  # e.g., "license", "adr", "dbs"
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ✅ Fetch driver credentials
    credentials = db.query(DriverCredentials).filter_by(user_id=driver_id).first()
    if not credentials:
        raise HTTPException(status_code=404, detail="Driver credentials not found")

    # ✅ Multi-tenant safety
    if current_user.organization_id != credentials.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to upload for this driver")

    # ✅ Upload file to S3
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    s3_key = f"driver_docs/{credentials.organization_id}/{driver_id}/{unique_filename}"
    
    try:
        storage.upload_fileobj(file.file, s3_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

    # ✅ Deactivate old documents of the same type
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == doc_type,
        Document.is_active == True
    ).update({"is_active": False})

    # ✅ Create new Document record
    document = Document(
        user_id=driver_id,
        organization_id=credentials.organization_id,
        credential_id=credentials.id,
        filename=file.filename,
        attachment_url=s3_key,  # store S3 key
        doc_type=doc_type,
        is_active=True
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="upload_driver_credential",
        details=f"{current_user.role} uploaded new {doc_type} for driver {driver_id} (org={credentials.organization_id})"
    )

    # ✅ Return presigned URL for frontend
    file_url = storage.generate_download_url(s3_key)

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


@router.get("/{driver_id}/documents")
def list_driver_documents(
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
    return [
        {
            "id": str(doc.id),
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "uploaded_at": doc.upload_time,
            "active": doc.is_active,
            "file_url": storage.generate_download_url(doc.attachment_url) if doc.attachment_url else None
        }
        for doc in documents
    ]
    
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.dependencies import require_role
from app.database import get_db
from app.models import Document, User
from app.dependencies import get_current_user  # Assuming you already have RBAC utils
from app.schemas import DocumentOut  # schema for returning documents


@router.get("/admin/documents")
def list_all_driver_documents(
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

    # --- 2. Prepare output with S3 presigned URLs ---
    results = []
    for doc in documents:
        results.append({
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "file_url": storage.generate_download_url(doc.attachment_url) if doc.attachment_url else None,
            "uploaded_at": doc.upload_time,
            "is_active": doc.is_active,
            "driver_id": str(doc.user.id),
            "driver_name": doc.user.full_name,
            "driver_email": doc.user.email,
        })

    return {
        "organization_id": str(current_user.organization_id),
        "documents": results
    }
@router.patch("/drivers/{driver_id}/documents/{document_id}/activate")
def activate_document(
    driver_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    # --- Fetch driver ---
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

    # --- Archive other docs of same type ---
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == document.doc_type,
        Document.id != document.id
    ).update({Document.is_active: False})

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

    # --- Generate presigned S3 URL for frontend ---
    file_url = storage.generate_download_url(document.file_path) if document.file_path else None

    return {
        "detail": "Document activated",
        "document_id": str(document.id),
        "doc_type": document.doc_type,
        "is_active": document.is_active,
        "file_url": file_url
    }
    
from datetime import datetime, timedelta    
@router.get("/drivers/{driver_id}/documents/expiry-status")
def check_document_expiry(
    driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if any driver document is expired or nearing expiry.
    Returns status: valid | expiring_soon | expired
    Includes S3 presigned URL for download.
    """
    driver = db.query(User).filter(
        User.id == driver_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    documents = db.query(Document).filter(
        Document.user_id == driver_id,
        Document.expiry_date.isnot(None)
    ).all()

    results = []
    warning_period = timedelta(days=30)
    now = datetime.utcnow()

    for doc in documents:
        if doc.expiry_date < now:
            status = "expired"
        elif doc.expiry_date < now + warning_period:
            status = "expiring_soon"
        else:
            status = "valid"

        # Generate presigned URL if using S3
        file_url = None
        if doc.file_path:
            file_url = storage.generate_download_url(doc.file_path)  # your S3 helper

        results.append({
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "expiry_date": doc.expiry_date,
            "status": status,
            "days_remaining": (doc.expiry_date - now).days,
            "file_url": file_url
        })

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
@router.get("/", response_model=List[schemas.DriverCredentialsOut])
def get_all_driver_credentials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # --- Fetch credentials based on role ---
    query = db.query(models.DriverCredentials).filter(
        models.DriverCredentials.organization_id == current_user.organization_id
    )

    if current_user.role == "driver":
        query = query.filter(models.DriverCredentials.user_id == current_user.id)
    elif current_user.role not in {"admin", "driver"}:
        raise HTTPException(status_code=403, detail="Not authorized")

    creds = query.all()

    # --- Add S3 URLs for each credential's documents ---
    creds_out = []
    for cred in creds:
        # Fetch associated documents
        documents = db.query(models.Document).filter(
            models.Document.credential_id == cred.id,
            models.Document.is_active == True
        ).all()

        doc_urls = []
        for doc in documents:
            s3_url = storage.generate_download_url(doc.file_path)  # presigned S3 URL
            doc_urls.append({
                "doc_type": doc.doc_type,
                "url": s3_url,
                "uploaded_at": doc.upload_time
            })

        creds_out.append({
            **cred.__dict__,
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

@router.get("/{credentials_id}", response_model=schemas.DriverCredentialsOut)
def get_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    creds = db.query(models.DriverCredentials).filter(models.DriverCredentials.id == credentials_id).first()
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # Multi-tenant check
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Drivers can only view their own credentials
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only view their own credentials")

    # Fetch associated active documents
    documents = db.query(models.Document).filter(
        models.Document.credential_id == creds.id,
        models.Document.is_active == True
    ).all()

    doc_urls = []
    for doc in documents:
        s3_url = storage.generate_download_url(doc.file_path)  # presigned S3 URL
        doc_urls.append({
            "doc_type": doc.doc_type,
            "url": s3_url,
            "uploaded_at": doc.upload_time
        })

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="view_driver_credentials",
        details=f"{current_user.role} viewed credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    # Combine credential data + documents
    response_data = {
        **creds.__dict__,
        "documents": doc_urls
    }

    return response_data
# ✅ Update driver credentials
@router.put("/{credentials_id}", response_model=schemas.DriverCredentialsOut)
def update_driver_credentials(
    credentials_id: UUID,
    update_data: schemas.DriverCredentialsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    creds = db.query(models.DriverCredentials).filter(models.DriverCredentials.id == credentials_id).first()
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # Multi-tenant access check
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Drivers can update only their own credentials
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only update their own credentials")

    # Apply updates
    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(creds, key, value)

    db.commit()
    db.refresh(creds)

    # Fetch associated active documents and generate S3 presigned URLs
    documents = db.query(models.Document).filter(
        models.Document.credential_id == creds.id,
        models.Document.is_active == True
    ).all()

    doc_urls = []
    for doc in documents:
        s3_url = storage.generate_download_url(doc.file_path)
        doc_urls.append({
            "doc_type": doc.doc_type,
            "url": s3_url,
            "uploaded_at": doc.upload_time
        })

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="update_driver_credentials",
        details=f"{current_user.role} updated credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    response_data = {
        **creds.__dict__,
        "documents": doc_urls
    }

    return response_data


# ✅ Delete driver credentials
@router.delete("/{credentials_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Fetch credentials
    creds = db.query(models.DriverCredentials).filter(models.DriverCredentials.id == credentials_id).first()
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # Multi-tenant access
    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Driver role check
    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only delete their own credentials")

    # Delete associated S3 documents
    documents = db.query(models.Document).filter(models.Document.credential_id == creds.id).all()
    for doc in documents:
        try:
            storage.delete_file(doc.file_path)  # Delete from S3
        except Exception as e:
            # Log error but continue deletion
            print(f"Failed to delete {doc.file_path} from S3: {e}")
        db.delete(doc)

    # Delete credentials
    db.delete(creds)
    db.commit()

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delete_driver_credentials",
        details=f"{current_user.role} deleted credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    return None