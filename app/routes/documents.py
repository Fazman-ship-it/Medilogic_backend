from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os

from app.dependencies import get_db, get_current_user
from app.models import Document, User
from app.schemas import DocumentOut
from app.utilites.logging import log_activity

router = APIRouter()

UPLOAD_FOLDER = "app/static/uploads/documents"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large. Max size is {MAX_FILE_SIZE_MB} MB")

    filename = f"{datetime.utcnow().timestamp()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save file.")

    # Save document metadata to DB
    new_doc = Document(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        filename=file.filename,
        file_path=file_path,
        upload_time=datetime.utcnow()
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # Optional: Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="document_uploaded",
        details=f"{current_user.name} uploaded '{file.filename}'",
        document_id=new_doc.id
    )

    return {"filename": file.filename, "url": f"/static/uploads/documents/{filename}"}


@router.get("/", response_model=list[DocumentOut])
def get_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.organization_id == current_user.organization_id
    ).all()


@router.get("/download/{doc_id}")
def download_my_document(
    doc_id: int,
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
        raise HTTPException(status_code=403, detail="Not authorized to download this document")

    return FileResponse(path=doc.file_path, filename=doc.filename, media_type="application/octet-stream")


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
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
        raise HTTPException(status_code=403, detail="Not authorized to delete this document")

    # Remove file from filesystem
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()

    log_activity(
        db=db,
        user_id=current_user.id,
        action="document_deleted",
        details=f"{current_user.name} deleted document '{doc.filename}' (ID: {doc.id})",
        document_id=doc.id
    )

    return {"message": f"Document ID {doc.id} deleted successfully."}