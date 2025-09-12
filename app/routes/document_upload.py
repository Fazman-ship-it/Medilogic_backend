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
from typing import Optional
from app.config import settings

router = APIRouter(
    prefix="/documents",
    tags=["Document Upload"]
)
from app.utilites.storage_utilites import upload_file_to_s3_async, generate_presigned_url_async

@router.post("/upload", response_model=schemas.DocumentUploadOut)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("general"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload a document to S3 and store metadata in DB."""

    # ✅ Only allow PDFs
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # Generate unique S3 key
    file_ext = os.path.splitext(file.filename)[1]
    file_id = uuid4()
    s3_key = f"documents/{current_user.organization_id}/{file_id}{file_ext}"

    # ✅ Upload asynchronously to S3
    try:
        await upload_file_to_s3_async(file, prefix=f"documents/{current_user.organization_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")

    # Save metadata to DB
    document = models.Document(
        id=file_id,
        filename=file.filename,
        file_path=s3_key,
        doc_type=doc_type,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        upload_time=datetime.utcnow(),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # ✅ Return presigned URL
    presigned_url = await generate_presigned_url_async(document.file_path)

    return schemas.DocumentUploadOut(
        id=document.id,
        filename=document.filename,
        doc_type=document.doc_type,
        upload_time=document.upload_time,
        organization_id=document.organization_id,
        user_id=document.user_id,
        file_url=presigned_url,
    )


@router.get("/", response_model=List[schemas.DocumentUploadOut])
async def list_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    doc_type: Optional[str] = None,
):
    """List uploaded documents with optional filtering and presigned URLs."""

    query = db.query(models.Document)

    # Admin sees only their org, Super Admin sees all
    if current_user.role == "admin":
        query = query.filter(models.Document.organization_id == current_user.organization_id)

    if doc_type:
        query = query.filter(models.Document.doc_type == doc_type)

    documents = query.order_by(models.Document.upload_time.desc()).all()

    result = []
    for d in documents:
        presigned_url = await generate_presigned_url_async(d.file_path)
        result.append(
            schemas.DocumentUploadOut(
                id=d.id,
                filename=d.filename,
                doc_type=d.doc_type,
                upload_time=d.upload_time,
                organization_id=d.organization_id,
                user_id=d.user_id,
                file_url=presigned_url,
            )
        )

    return result