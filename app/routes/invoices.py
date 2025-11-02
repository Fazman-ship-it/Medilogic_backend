from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from datetime import datetime
from uuid import uuid4
from app.utilites.logging import log_activity
from fastapi.responses import StreamingResponse
import csv
import io
from io import BytesIO
from typing import List,Optional,Literal
from app.dependencies import require_role
from uuid import UUID
from app.utilites.time_utilities import now_utc
from datetime import timezone, datetime
router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"]
)

@router.post("/generate", response_model=schemas.InvoiceResponse)
def generate_invoice(
    invoice_data: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ Access organization_id
):
    # ✅ 1. Validate client exists
    client = db.query(models.User).filter(models.User.id == invoice_data.client_id).first()
    if not client or client.role != "client":
        raise HTTPException(status_code=404, detail="Client not found")

    # ✅ 2. Check for duplicate invoice in same range within this org
    existing_invoice = db.query(models.Invoice).filter(
        models.Invoice.client_id == invoice_data.client_id,
        models.Invoice.start_date == invoice_data.start_date,
        models.Invoice.end_date == invoice_data.end_date,
        models.Invoice.organization_id == current_user.organization_id  # ✅ enforce tenant isolation
    ).first()

    if existing_invoice:
        raise HTTPException(status_code=400, detail="Invoice already exists for this client and date range.")

    # ✅ 3. Filter trips for invoice, scoped to same org
    trips = db.query(models.Trip).filter(
        models.Trip.client_id == invoice_data.client_id,
        models.Trip.created_at >= invoice_data.start_date,
        models.Trip.created_at <= invoice_data.end_date,
        models.Trip.organization_id == current_user.organization_id  # ✅ enforce tenant isolation
    ).all()

    if not trips:
        raise HTTPException(status_code=400, detail="No trips found for invoice range.")

    total_amount = sum([trip.cost or 0 for trip in trips])

    # ✅ 4. Generate unique reference code if not provided
    ref_base = f"{client.name[:6].upper().replace(' ', '')}"
    generated_ref = f"INV-{invoice_data.start_date:%Y-%m}-{ref_base}-{uuid4().hex[:4].upper()}"

    # ✅ 5. Create invoice — inject org_id from current_user
    invoice = models.Invoice(
        invoice_number=f"INV-{uuid4().hex[:8]}",
        client_id=invoice_data.client_id,
        organization_id=current_user.organization_id,  # ✅ securely injected
        start_date=invoice_data.start_date,
        end_date=invoice_data.end_date,
        amount=total_amount,
        due_date=invoice_data.due_date,
        reference_code=invoice_data.reference_code or generated_ref,
        status="unpaid",
        generated_at=datetime.now(timezone.utc)
    )

    try:
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Duplicate invoice reference code. Try again.")

    return invoice

@router.get("/admin", response_model=List[schemas.InvoiceResponse])
def list_all_invoices(
    client_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, regex="^(paid|unpaid|overdue)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    due_date_from: Optional[datetime] = None,
    due_date_to: Optional[datetime] = None, 
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ access organization
):
    # ✅ Base query scoped to the admin’s organization
    query = db.query(models.Invoice).filter(
        models.Invoice.organization_id == current_user.organization_id
    )

    if client_id:
        query = query.filter(models.Invoice.client_id == client_id)

    if status:
        query = query.filter(models.Invoice.status == status)

    if start_date:
        query = query.filter(models.Invoice.start_date >= start_date)

    if end_date:
        query = query.filter(models.Invoice.end_date <= end_date)

    if due_date_from:
        query = query.filter(models.Invoice.due_date >= due_date_from)

    if due_date_to:
        query = query.filter(models.Invoice.due_date <= due_date_to)        

    invoices = query.offset(skip).limit(limit).all()
    return invoices

@router.get("/client/{client_id}", response_model=List[schemas.InvoiceResponse])
def list_client_invoices(
    client_id: UUID,
    status: Optional[str] = Query(None, regex="^(paid|unpaid|overdue)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    due_date_from: Optional[datetime] = None,
    due_date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ✅ Use direct user access
):
    # ✅ Allow only the matching client or an admin
    if current_user.role == "client" and current_user.id != client_id:
        raise HTTPException(status_code=403, detail="Access denied. You can only view your own invoices.")
    if current_user.role not in ["client", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    # ✅ Base query filtered by org
    query = db.query(models.Invoice).filter(
        models.Invoice.client_id == client_id,
        models.Invoice.organization_id == current_user.organization_id  # ✅ tenant isolation
    )

    if status:
        query = query.filter(models.Invoice.status == status)
    if start_date:
        query = query.filter(models.Invoice.start_date >= start_date)
    if end_date:
        query = query.filter(models.Invoice.end_date <= end_date)
    if due_date_from:
        query = query.filter(models.Invoice.due_date >= due_date_from)
    if due_date_to:
        query = query.filter(models.Invoice.due_date <= due_date_to)

    return query.all()

@router.delete("/{invoice_id}", status_code=200)
def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    # ✅ Only allow delete if invoice belongs to user's organization
    invoice = db.query(models.Invoice).filter(
        models.Invoice.id == invoice_id,
        models.Invoice.organization_id == current_user.organization_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice with ID {invoice_id} not found")

    db.delete(invoice)
    db.commit()

    # ✅ Log the deletion
    log_activity(
        db=db,
        user_id=current_user.id,
        action="invoice_deleted",
        details=f"Admin {current_user.name} deleted invoice ID {invoice_id}",
    )

    return {"message": f"Invoice with ID {invoice_id} deleted successfully."}

@router.get("/export", response_class=StreamingResponse)
def export_invoices_csv(
    client_id: Optional[UUID] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ Access org
):
    # ✅ Base query with JOIN to include client name in one query
    query = (
        db.query(
            models.Invoice,
            models.User.name.label("client_name")
        )
        .join(models.User, models.Invoice.client_id == models.User.id)
        .filter(models.Invoice.organization_id == current_user.organization_id)
    )

    # ✅ Apply filters
    if client_id:
        query = query.filter(models.Invoice.client_id == client_id)
    if status:
        query = query.filter(models.Invoice.status == status)

    results = query.all()
    if not results:
        raise HTTPException(status_code=404, detail="No invoices found for export")

    # ✅ Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice ID",
        "Client ID",
        "Client Name",
        "Organization ID",
        "Amount (£)",
        "Status",
        "Reference Code",
        "Invoice Number",
        "Start Date",
        "End Date",
        "Due Date",
        "Generated At"
    ])

    for invoice, client_name in results:
        writer.writerow([
            str(invoice.id),
            str(invoice.client_id),
            client_name or "Unknown",
            str(invoice.organization_id),
            invoice.amount,
            invoice.status,
            invoice.reference_code,
            invoice.invoice_number,
            invoice.start_date.strftime("%Y-%m-%d") if invoice.start_date else "",
            invoice.end_date.strftime("%Y-%m-%d") if invoice.end_date else "",
            invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
            invoice.generated_at.strftime("%Y-%m-%d %H:%M:%S") if invoice.generated_at else "",
        ])

    output.seek(0)

    # ✅ Log export activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="invoice_export_csv",
        details=f"Admin {current_user.name} exported {len(results)} invoices to CSV (JOIN optimized)"
    )

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices_export.csv"}
    )
    
@router.patch("/{invoice_id}/update-status", response_model=schemas.InvoiceResponse)
def update_invoice_status(
    invoice_id: UUID,
    body: schemas.InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    invoice = db.query(models.Invoice).filter(
        models.Invoice.id == invoice_id,
        models.Invoice.organization_id == current_user.organization_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # ✅ Use the correct field name
    invoice.status = body.status  

    db.commit()
    db.refresh(invoice)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="invoice_status_updated",
        details=f"Admin {current_user.name} changed invoice {invoice.invoice_number} status to {invoice.status}",
    )

    return invoice
    
@router.get("/{invoice_id}", response_model=schemas.InvoiceResponse)
def get_invoice_detail(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🔍 Fetch the invoice
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # 🔒 Ensure it belongs to same organization
    if invoice.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 🔒 Role access — clients can only see their own
    if current_user.role == "client" and invoice.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own invoices")

    return invoice
    
import csv
import io
from fastapi.responses import StreamingResponse

@router.get("/{invoice_id}/download")
def download_invoice_csv(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    📦 Download a single invoice as a CSV file.
    - Clients can only download their own invoices.
    - Admins can download any invoice in their organization.
    - Includes audit logging for compliance.
    """

    # 🔍 Fetch invoice
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # 🔒 Tenant isolation: ensure same organization
    if invoice.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 🔒 Restrict clients to their own invoices
    if current_user.role == "client" and invoice.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only download your own invoices")

    # 🔍 Fetch client details
    client = db.query(models.User).filter(models.User.id == invoice.client_id).first()
    client_name = client.name if client else "Unknown"
    client_id = str(invoice.client_id) if invoice.client_id else "N/A"

    # 🧾 Generate CSV in-memory
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)

    writer.writerow([
        "Invoice ID",
        "Client ID",
        "Client Name",
        "Amount (£)",
        "Status",
        "Reference Code",
        "Invoice Number",
        "Due Date",
        "Generated At",
        "Organization"
    ])

    writer.writerow([
        str(invoice.id),
        client_id,
        client_name,
        invoice.amount,
        invoice.status,
        invoice.reference_code,
        invoice.invoice_number,
        invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        invoice.generated_at.strftime("%Y-%m-%d %H:%M:%S") if invoice.generated_at else "",
        invoice.organization.name if invoice.organization else "",
    ])

    csv_buffer.seek(0)

    # 🧠 Log activity for audit and compliance
    log_activity(
        db=db,
        user_id=current_user.id,
        action="invoice_csv_downloaded",
        details=f"User {current_user.name} downloaded invoice {invoice.invoice_number or invoice.id}"
    )

    # 📦 Return as downloadable CSV file
    filename = f"invoice_{invoice.invoice_number or invoice.id}.csv"
    return StreamingResponse(
        csv_buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )