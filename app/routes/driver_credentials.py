from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import shutil, os, uuid
from app.database import get_db
from app.models import DriverCredentials, Document
from app.utilites.logging import log_activity
from app.dependencies import get_current_user
from app import models,schemas

router = APIRouter(prefix="/drivers", tags=["Driver Credentials"])

# ✅ Static upload directory
UPLOAD_DIR = "static/driver_docs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/{driver_id}/upload-credential")
async def upload_driver_credential(
    driver_id: uuid.UUID,
    doc_type: str,  # e.g., "license", "adr", "dbs"
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ✅ Check if driver credentials exist
    credentials = db.query(DriverCredentials).filter_by(user_id=driver_id).first()
    if not credentials:
        raise HTTPException(status_code=404, detail="Driver credentials not found")

    # ✅ Multi-tenant check
    if current_user.organization_id != credentials.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to upload for this driver")

    # ✅ Save file under static directory
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # ✅ Deactivate old documents of same type
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == doc_type,
        Document.is_active == True
    ).update({"is_active": False})

    # ✅ Create new Document entry
    document = Document(
        user_id=driver_id,
        organization_id=credentials.organization_id,
        credential_id=credentials.id,
        filename=file.filename,
        file_path=file_path,  # full local path (optional: store relative path)
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

    # ✅ Return clean response
    return {
        "message": f"{doc_type} uploaded successfully",
        "document_id": str(document.id),
        "file_url": f"/{file_path}",  # served via StaticFiles
        "is_active": document.is_active
    }
    

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.database import get_db
from app.models import Document, User
from app.auth import get_current_user


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
    # Ensure the driver exists
    driver = db.query(User).filter(User.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Multi-tenant restriction: must belong to the same organization
    if driver.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # Role-based access:
    if current_user.role == "driver":
        # Driver can only access their own credentials
        if current_user.id != driver_id:
            raise HTTPException(status_code=403, detail="Drivers can only view their own documents")

    elif current_user.role == "admin":
        # Admin can view all drivers in their organization
        pass  # already restricted by organization check above

    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Build query with optional filters
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

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="list_driver_documents",
        details=f"{current_user.role} listed documents for driver {driver_id}"
    )

    return [
        {
            "id": str(doc.id),
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "uploaded_at": doc.upload_time,
            "active": doc.is_active,
            "file_path": doc.file_path  # Later replace with signed URL
        }
        for doc in documents
    ]    
    
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.dependencies import require_role
from app.database import get_db
from app.models import Document, User
from app.auth import get_current_user  # Assuming you already have RBAC utils
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
    # Get all documents in the same organization
    documents = (
        db.query(Document)
        .join(User, Document.user_id == User.id)
        .filter(User.organization_id == current_user.organization_id)
        .all()
    )

    results = []
    for doc in documents:
        results.append({
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "file_path": doc.file_path,
            "uploaded_at": doc.created_at,
            "is_active": doc.is_active,
            "driver_id": str(doc.user.id),
            "driver_name": doc.user.name,
            "driver_email": doc.user.email,
        })

    return {"organization_id": str(current_user.organization_id), "documents": results}

@router.patch("/drivers/{driver_id}/documents/{document_id}/activate")
def activate_document(
    driver_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))  # admin only
):
    """
    Mark a document as active and archive others of same type.
    """
    driver = db.query(User).filter(
        User.id == driver_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == driver_id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Archive all other docs of same type
    db.query(Document).filter(
        Document.user_id == driver_id,
        Document.doc_type == document.doc_type
    ).update({Document.is_active: False})

    # Set this doc active
    document.is_active = True
    db.commit()
    db.refresh(document)

    return {"detail": "Document activated", "document_id": str(document.id)}

from datetime import datetime, timedelta

@router.get("/drivers/{driver_id}/documents/expiry-status")
def check_document_expiry(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if any driver document is expired or nearing expiry.
    """
    driver = db.query(User).filter(
        User.id == driver_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Only driver themselves or admins can view
    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    documents = db.query(Document).filter(Document.user_id == driver_id).all()
    results = []
    warning_period = timedelta(days=30)  # 30-day warning

    for doc in documents:
        if not doc.expiry_date:
            continue  # skip docs without expiry

        status = "valid"
        if doc.expiry_date < datetime.utcnow():
            status = "expired"
        elif doc.expiry_date < datetime.utcnow() + warning_period:
            status = "expiring_soon"

        results.append({
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "expiry_date": doc.expiry_date,
            "status": status
        })

    return {"driver_id": str(driver.id), "expiry_status": results}

# app/routes/driver_credentials.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app import models, schemas, database
from app.dependencies import get_current_user  # JWT user dependency



# ✅ Create driver credentials
@router.post("/", response_model=schemas.DriverCredentialsOut)
def create_driver_credentials(
    credentials: schemas.DriverCredentialsCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Check same organization
    if current_user.organization_id != credentials.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # Drivers can ONLY create their own credentials
    if current_user.role == "driver" and current_user.id != credentials.user_id:
        raise HTTPException(status_code=403, detail="Drivers can only create their own credentials")

    # Admin can create for any driver in same org
    if current_user.role == "admin":
        driver = db.query(models.User).filter(
            models.User.id == credentials.user_id,
            models.User.organization_id == current_user.organization_id
        ).first()
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found in your organization")

    db_credentials = models.DriverCredentials(**credentials.dict())
    db.add(db_credentials)
    db.commit()
    db.refresh(db_credentials)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="create_driver_credentials",
        details=f"{current_user.role} created credentials {db_credentials.id} for driver {db_credentials.user_id} (org={db_credentials.organization_id})"
    )

    return db_credentials


# ✅ Get all driver credentials
@router.get("/", response_model=List[schemas.DriverCredentialsOut])
def get_all_driver_credentials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    creds = []
    if current_user.role == "admin":
        creds = (
            db.query(models.DriverCredentials)
            .filter(models.DriverCredentials.organization_id == current_user.organization_id)
            .all()
        )

    elif current_user.role == "driver":
        creds = (
            db.query(models.DriverCredentials)
            .filter(
                models.DriverCredentials.organization_id == current_user.organization_id,
                models.DriverCredentials.user_id == current_user.id,
            )
            .all()
        )
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="list_driver_credentials",
        details=f"{current_user.role} listed {len(creds)} driver credentials (org={current_user.organization_id})"
    )

    return creds


# ✅ Get single driver credentials
@router.get("/{credentials_id}", response_model=schemas.DriverCredentialsOut)
def get_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    creds = db.query(models.DriverCredentials).filter(models.DriverCredentials.id == credentials_id).first()
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only view their own credentials")

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="view_driver_credentials",
        details=f"{current_user.role} viewed credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    return creds

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

    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only update their own credentials")

    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(creds, key, value)

    db.commit()
    db.refresh(creds)

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="update_driver_credentials",
        details=f"{current_user.role} updated credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    return creds


# ✅ Delete driver credentials
@router.delete("/{credentials_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver_credentials(
    credentials_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    creds = db.query(models.DriverCredentials).filter(models.DriverCredentials.id == credentials_id).first()
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found")

    if creds.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.role == "driver" and creds.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Drivers can only delete their own credentials")

    db.delete(creds)
    db.commit()

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delete_driver_credentials",
        details=f"{current_user.role} deleted credentials {creds.id} for driver {creds.user_id} (org={creds.organization_id})"
    )

    return None    