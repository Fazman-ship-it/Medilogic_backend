import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException,Form
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime
from app.database import get_db
from app.models import Document, User
from app.schemas import DocumentUploadOut
from app.dependencies import get_current_user
from typing import List
from app import models, schemas
from app.storage import S3Storage
from typing import Optional
from app.config import settings

router = APIRouter(
    prefix="/documents",
    tags=["Document Upload"]
)
storage = S3Storage()

@router.post("/upload", response_model=schemas.DocumentUploadOut)
def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("general"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a document to S3 and store metadata in DB."""
    
    # ✅ Only allow PDFs
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    # Generate unique S3 key
    file_ext = os.path.splitext(file.filename)[1]
    file_id = uuid4()  # ✅ keep as UUID
    s3_key = f"documents/{current_user.organization_id}/{file_id}{file_ext}"
    
    # Upload file to S3
    storage.upload_fileobj(file.file, s3_key)
    
    # Save metadata to DB
    document = models.Document(
        id=file_id,
        filename=file.filename,
        file_path=s3_key,  # ✅ match your model column
        doc_type=doc_type,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        upload_time=datetime.utcnow(),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # ✅ Return presigned URL for frontend access
    return schemas.DocumentUploadOut(
        id=document.id,
        filename=document.filename,
        doc_type=document.doc_type,
        upload_time=document.upload_time,
        organization_id=document.organization_id,
        user_id=document.user_id,
        file_url=storage.generate_download_url(document.file_path)  # ✅ match schema
    )

@router.get("/", response_model=List[schemas.DocumentUploadOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_type: Optional[str] = None
):
    """List uploaded documents with optional filtering and presigned URLs."""
    
    query = db.query(models.Document)
    
    # Admin sees only their org, Super Admin sees all
    if current_user.role == "admin":
        query = query.filter(models.Document.organization_id == current_user.organization_id)
    
    if doc_type:
        query = query.filter(models.Document.doc_type == doc_type)
    
    documents = query.order_by(models.Document.upload_time.desc()).all()
    
    # ✅ Generate presigned URLs for all documents
    return [
        schemas.DocumentUploadOut(
            id=d.id,
            filename=d.filename,
            doc_type=d.doc_type,
            upload_time=d.upload_time,
            organization_id=d.organization_id,
            user_id=d.user_id,
            file_url=storage.generate_download_url(d.file_path)  # ✅ match DB + schema
        )
        for d in documents
    ]
    