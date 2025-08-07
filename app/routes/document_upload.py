import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime
from app.database import get_db
from app.models import Document, User
from app.schemas import DocumentUploadOut
from app.dependencies import get_current_user
from typing import List

router = APIRouter(
    prefix="/documents",
    tags=["Document Upload"]
)

UPLOAD_DIR = "static/uploads/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", response_model=DocumentUploadOut)
def upload_document(
    file: UploadFile = File(...),
    doc_type: str = "general",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    📁 Upload a document (PDFs, Certificates, etc.)
    - Stores in static/uploads/documents
    - Tracks user, doc_type, org_id
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_id = str(uuid4())
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{file_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)

    with open(file_path, "wb") as f:
        f.write(file.file.read())

    document = Document(
        id=file_id,
        filename=file.filename,
        file_path=f"/static/uploads/documents/{new_filename}",
        doc_type=doc_type,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        upload_time=datetime.utcnow()
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return document

@router.get("/", response_model=List[DocumentUploadOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_type: str = None
):
    """
    📄 List uploaded documents
    - Filter by doc_type (optional)
    - Admin: only org documents
    - Super Admin: all documents
    """
    query = db.query(Document)
    if current_user.role == "admin":
        query = query.filter(Document.organization_id == current_user.organization_id)

    if doc_type:
        query = query.filter(Document.doc_type == doc_type)

    return query.order_by(Document.upload_time.desc()).all()