from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os
from uuid import UUID
from app.dependencies import get_db, get_current_user
from app.models import Document, User
from app.schemas import DocumentOut
from app.utilites.logging import log_activity
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4, UUID
from datetime import datetime
from app.models import Document, User
from app.database import get_db
from app.auth import get_current_user
from app.utilites.storage_utilites import s3
from app.schemas import DocumentOut, DocumentDownloadOut, DocumentDeleteOut
from typing import Optional
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".docx"}
MAX_FILE_SIZE_MB = 5

def get_extension(filename: str):
    return os.path.splitext(filename)[1].lower()

@router.post("/upload/", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ext = get_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed.")

    contents = await file.read()
    size_mb = len(contents) / (1024*1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large. Max size is {MAX_FILE_SIZE_MB} MB")

    file_id = str(uuid4())
    s3_key = f"documents/{current_user.organization_id}/{file_id}{ext}"

    try:
        # Upload to S3
        s3.upload_file_to_s3(contents, s3_key, file.content_type)

        # Save metadata in DB
        doc = Document(
            id=file_id,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            filename=file.filename,          # original filename
            file_path=s3_key,                # S3 key
            mime_type=file.content_type,     # ✅ store type
            upload_time=datetime.utcnow()
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Log action
        log_activity(
            db=db,
            user_id=current_user.id,
            action="file_upload",
            details=f"Uploaded {file.filename} -> {s3_key}"
        )

    except Exception as e:
        db.rollback()
        # optional cleanup if S3 succeeded but DB failed
        try:
            s3.delete_object(s3_key)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {
        "filename": doc.filename,
        "document_id": doc.id,
        "url": s3.generate_presigned_url(s3_key)
    }

@router.get("/", response_model=list[DocumentOut])
def get_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    docs = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.organization_id == current_user.organization_id
    ).all()

    result = []
    for d in docs:
        presigned = s3.generate_presigned_url(d.file_path)
        result.append(
            DocumentOut(
                id=d.id,
                filename=d.filename,
                file_path=d.file_path,
                mime_type=getattr(d, "mime_type", None),
                upload_time=d.upload_time,
                url=presigned
            )
        )

    return result

# routes/documents.py
@router.get("/download/{doc_id}", response_model=DocumentDownloadOut)
def download_my_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.organization_id == current_user.organization_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # ✅ Access control
    if doc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # ✅ Generate short-lived presigned URL
    presigned_url = s3.generate_presigned_url(doc.file_path, expires_in=600)

    return DocumentDownloadOut(url=presigned_url)

# routes/documents.py
@router.delete("/{doc_id}", response_model=DocumentDeleteOut)
def delete_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.organization_id == current_user.organization_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.user_id != current_user.id and current_user.role not in {"admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Not authorized")

    # ✅ Delete from S3 (safe handling)
    try:
        s3.delete_file_from_s3(doc.file_path)
    except Exception as e:
        # log error but still remove DB record
        print(f"⚠️ S3 delete failed for {doc.file_path}: {e}")

    # ✅ Remove DB record
    db.delete(doc)
    db.commit()

    return DocumentDeleteOut(
        message=f"Document deleted successfully",
        document_id=doc.id
    )
