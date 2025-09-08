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

    # Upload to S3
    s3.upload_file_to_s3(contents, s3_key, file.content_type)

    # Save metadata in DB
    doc = Document(
        id=file_id,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        filename=file.filename,
        file_path=s3_key,
        upload_time=datetime.utcnow()
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "filename": file.filename,
        "document_id": doc.id,
        "url": s3.generate_presigned_url(s3_key)
    }


@router.get("/", response_model=list[Document])
def get_my_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    docs = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.organization_id == current_user.organization_id
    ).all()
    # Add presigned URLs
    for d in docs:
        d.url = s3.generate_presigned_url(d.file_path)
    return docs


@router.get("/download/{doc_id}")
def download_my_document(doc_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.organization_id == current_user.organization_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Return presigned URL instead of raw file
    return {"url": s3.generate_presigned_url(doc.file_path)}


@router.delete("/{doc_id}")
def delete_document(doc_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.organization_id == current_user.organization_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Delete from S3
    s3.delete_file_from_s3(doc.file_path)

    db.delete(doc)
    db.commit()

    return {"message": f"Document {doc.id} deleted successfully"}