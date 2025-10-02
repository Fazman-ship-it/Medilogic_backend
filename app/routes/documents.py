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
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async, delete_file_from_s3
from app.utilites.logging import log_activity
from app.utilites.time_utilities import now_utc
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
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large. Max size is {MAX_FILE_SIZE_MB} MB")

    file_id = uuid4()   # ✅ use UUID not str
    s3_key = f"documents/{current_user.organization_id}/{file_id}{ext}"

    try:
        # Upload to S3
        await upload_file_to_s3_async(file, prefix=f"documents/{current_user.organization_id}")

        # Save metadata in DB
        doc = Document(
            id=file_id,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            filename=file.filename,
            file_path=s3_key,
            mime_type=file.content_type,
            upload_time=now_utc()
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        log_activity(
            db=db,
            user_id=current_user.id,
            action="file_upload",
            details=f"Uploaded {file.filename} -> {s3_key}"
        )

    except Exception as e:
        db.rollback()
        try:
            await delete_file_from_s3(s3_key)   # ✅ async cleanup
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    presigned_url = await generate_presigned_url_async(s3_key)

    return {
        "filename": doc.filename,
        "document_id": doc.id,
        "url": presigned_url
    }


@router.get("/", response_model=list[DocumentOut])
async def get_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    docs = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.organization_id == current_user.organization_id
    ).all()

    result = []
    for d in docs:
        presigned = await generate_presigned_url_async(d.file_path)
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


@router.get("/download/{doc_id}", response_model=DocumentDownloadOut)
async def download_my_document(
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

    if doc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    presigned_url = await generate_presigned_url_async(doc.file_path, expires_in=600)
    return DocumentDownloadOut(url=presigned_url)


@router.delete("/{doc_id}", response_model=DocumentDeleteOut)
async def delete_document(
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
    try:
        await delete_file_from_s3(doc.file_path)
    except Exception as e:
        print(f"⚠️ S3 delete failed for {doc.file_path}: {e}")

    db.delete(doc)
    db.commit()

    return DocumentDeleteOut(
        message="Document deleted successfully",
        document_id=doc.id
    )