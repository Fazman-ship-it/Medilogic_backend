from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Trip, Organization
from app.dependencies import get_current_user,get_db
from typing import List, Optional
from sqlalchemy import asc, desc
from datetime import datetime
import csv
import io
from fastapi.responses import StreamingResponse
from fpdf import FPDF
import joblib
import numpy as np
import os
from app.models import ComplianceStatus, Organization, User


router = APIRouter(prefix="/dashboard", tags=["Regulator Dashboard"])

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from app.database import get_db
from app.models import ComplianceStatus, Organization, User, AuditStatusEnum
from app.dependencies import get_current_user


@router.get("/compliance/summary/simple")
def get_simple_regulatory_compliance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Simplified Compliance Summary (Regulator only)
    🔐 Regulatory users see only organizations in their assigned country/state/region
    👑 Admins see all organizations
    """
    # 🔐 Check access
    if current_user.role not in ["regulatory"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    # 🌍 Region-based filtering (for regulators only)
    org_query = db.query(Organization)
    if current_user.role == "regulatory":
        org_query = org_query.filter(
            Organization.country == current_user.regulated_country,
            Organization.state == current_user. regulated_state,
            Organization.region == current_user. regulated_region
        )
    
    organizations = org_query.all()
    summaries = []

    for org in organizations:
        compliance = db.query(ComplianceStatus).filter_by(organization_id=org.id).first()
        if not compliance:
            continue

        # 🧠 Simplified logic for high-level compliance flag
        overall_compliant = (
            compliance.iso_27001_certified and
            compliance.nhs_dsp_toolkit_complete and
            compliance.cyber_essentials_ready and
            compliance.has_waste_license and
            compliance.audit_status == AuditStatusEnum.passed and
            not compliance.is_flagged_noncompliant
        )

        summaries.append({
            "organization_id": str(org.id),
            "organization_name": org.name,
            "country": org.country,
            "state": org.state,
            "region": org.region,
            "overall_compliant": overall_compliant
        })

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=None,
        action="simple_compliance_summary_viewed",
        details=f"{current_user.role.title()} user {current_user.name} viewed simplified compliance summary"
    )

    return {
        "total_organizations": len(summaries),
        "organization_summaries": summaries
    }

@router.get("/regulator")
def get_regulator_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    status: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("scheduled_time"),
    sort_order: Optional[str] = Query("asc"),
    format:Optional[str] = Query(None),
    limit:int = Query(100, ge=1, le=1000),
    offset:int= Query(0, ge=0)
    
):
    if current_user.role != "regulator":
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(Trip).join(Organization).filter(
        Organization.country == current_user.regulated_country,
        Organization.state == current_user.regulated_state
    )

    if current_user.regulated_region:
        query = query.filter(Organization.region == current_user.regulated_region)

    # 🔍 Apply Filters
    if start_date:
        query = query.filter(Trip.scheduled_time >= start_date)
    if end_date:
        query = query.filter(Trip.scheduled_time <= end_date)
    if status:
        query = query.filter(Trip.status == status)
    if delivery_type:
        query = query.filter(Trip.delivery_type == delivery_type)

    # ↕️ Sorting Logic
    sort_column = getattr(Trip, sort_by, Trip.scheduled_time)
    query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

    results = query.offset(offset).limit(limit).all()

    # 🎯 Export as CSV
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Trip ID", "Client", "delivery type", "Scheduled Time", "Cost", "Status"])
        for trip in results:
            writer.writerow([
                trip.id,
                trip.client_name,
                trip.delivery_type,
                trip.scheduled_time.strftime("%Y-%m-%d %H:%M"),
                trip.cost,
                trip.status
            ])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=regulator_report.csv"
        })

    # 🧾 Export as PDF
    if format == "pdf":
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        pdf.cell(200, 10, txt="Regulator Trip Report", ln=1, align="C")
        pdf.ln(5)
        for trip in results:
            pdf.multi_cell(0, 10, txt=f"Trip ID: {trip.id}\nClient: {trip.client_name}\nDelivery Type: {trip.delivery_type}\nTime:£{trip.scheduled_time}\nCost: {trip.cost}\nStatus: {trip.status}\n---")
            pdf.ln(2)

        response = StreamingResponse(io.BytesIO(pdf.output(dest='S').encode('latin1')), media_type="application/pdf")
        response.headers["Content-Disposition"] = "attachment; filename=regulator_report.pdf"
        return response

    # 🔁 Default: Return JSON
    return results


# ✅ Compliance rules logic
def evaluate_trip_compliance(trip):
    flags = []
    if trip.cost > 1000:
        flags.append("High cost trip")
    if trip.distance_km < 5 and trip.cost > 300:
        flags.append("Short trip with high cost")
    if trip.distance_km > 100:
        flags.append("Unusually long distance")
    if trip.scheduled_time < datetime.now():
        flags.append("Scheduled in the past")
    return flags


@router.get("/regulator/summary")
def regulator_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    format: Optional[str] = Query(None)
):
    if current_user.role != "regulator":
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Filter trips
    query = db.query(Trip).join(Organization).filter(
        Organization.country == current_user.regulated_country,
        Organization.state == current_user.regulated_state
    )

    if current_user.regulated_region:
        query = query.filter(Organization.region == current_user.regulated_region)

    if start_date:
        query = query.filter(Trip.scheduled_time >= start_date)
    if end_date:
        query = query.filter(Trip.scheduled_time <= end_date)

    trips = query.all()
    if not trips:
        return {"message": "No trips found for this regulator in the selected period."}

    # ✅ Summary stats
    total_trips = len(trips)
    total_distance = sum(t.distance_km for t in trips)
    total_cost = sum(t.cost for t in trips)
    average_cost = total_cost / total_trips
    average_distance = total_distance / total_trips

    # ✅ ML Prediction
    model_path = "trip_duration_model.pkl"
    if not os.path.exists(model_path):
        raise HTTPException(status_code=500, detail="ML model not found")

    model = joblib.load(model_path)
    features = np.array([[t.distance_km, t.cost] for t in trips])
    predicted_durations = model.predict(features)
    average_duration = round(predicted_durations.mean(), 2)

    # ✅ Compliance flags
    trip_flags = []
    for trip in trips:
        issues = evaluate_trip_compliance(trip)
        if issues:
            trip_flags.append({
                "trip_id": trip.id,
                "driver_name": trip.driver_name,
                "client_name": trip.client_name,
                "cost": trip.cost,
                "distance_km": trip.distance_km,
                "scheduled_time": trip.scheduled_time.isoformat(),
                "issues": issues
            })

    # ✅ Build response data
    summary_data = {
        "total_trips": total_trips,
        "average_cost": round(average_cost, 2),
        "average_distance_km": round(average_distance, 2),
        "predicted_average_duration_minutes": average_duration,
        "date_range": {
            "start": start_date.isoformat() if start_date else "N/A",
            "end": end_date.isoformat() if end_date else "N/A"
        },
        "currency": "£",
        "compliance_flags": trip_flags
    }

    # ✅ PDF Export
    if format == "pdf":
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.set_title("Regulator Trip Summary Report")

        pdf.cell(200, 10, txt="Trip AI Summary", ln=1, align="C")
        pdf.ln(5)

        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, txt=f"Date Range: {summary_data['date_range']['start']} to {summary_data['date_range']['end']}", ln=1)
        pdf.cell(0, 10, txt=f"Total Trips: {summary_data['total_trips']}", ln=1)
        pdf.cell(0, 10, txt=f"Average Cost: £{summary_data['average_cost']}", ln=1)
        pdf.cell(0, 10, txt=f"Average Distance: {summary_data['average_distance_km']} km", ln=1)
        pdf.cell(0, 10, txt=f"Predicted Avg Duration: {summary_data['predicted_average_duration_minutes']} mins", ln=1)

        # ✅ Compliance section
        if trip_flags:
            pdf.ln(5)
            pdf.set_font("Arial", 'B', size=11)
            pdf.cell(0, 10, txt="⚠️ Compliance Flags", ln=1)
            pdf.set_font("Arial", size=10)
            for flag in trip_flags:
                pdf.multi_cell(0, 8,
                    txt=f"- Trip ID {flag['trip_id']} | Driver: {flag['driver_name']} | Client: {flag['client_name']}\n"
                        f"  Issues: {', '.join(flag['issues'])}", border=0
                )
        else:
            pdf.ln(5)
            pdf.cell(0, 10, txt="✅ All trips passed compliance checks.", ln=1)

        buffer = io.BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=regulator_summary.pdf"
        })

    # ✅ JSON response
    return summary_data


from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from uuid import UUID

from app.database import get_db
from app.models import ComplianceStatus, Organization, User
from app.dependencies import require_role
from app.utilites.logging import log_activity
from app.utilites.compliance_exporter import generate_csv, generate_pdf, generate_compliance_chart
from app.models import AuditStatusEnum

@router.get("/compliance/regulatory-summary")
def get_regulatory_compliance_summary(
    region: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    export: Optional[str] = Query(None, regex="^(csv|pdf)$"),
    include_charts: Optional[bool] = Query(False),

    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["regulatory"]))
):
    """
    ✅ Get full compliance summary across all organizations (Regulatory Only)
    📁 Supports PDF/CSV Export, Region & Date Filters, Chart Output
    """
    if current_user.role != "regulatory":
        raise HTTPException(status_code=403, detail="Access denied. Regulatory only.")

    query = db.query(Organization)
    if region:
        query = query.filter(Organization.region == region)
    organizations = query.all()

    summaries = []
    compliant_count = 0

    for org in organizations:
        compliance_query = db.query(ComplianceStatus).filter_by(organization_id=org.id)

        if start_date:
            compliance_query = compliance_query.filter(ComplianceStatus.created_at >= start_date)
        if end_date:
            compliance_query = compliance_query.filter(ComplianceStatus.created_at <= end_date)

        compliance = compliance_query.first()
        if compliance:
            overall_compliant = (
                compliance.iso_27001_certified and
                compliance.nhs_dsp_toolkit_complete and
                compliance.cyber_essentials_ready and
                compliance.has_waste_license and
                compliance.fire_risk_assessment_complete and
                compliance.gdpr_policy_uploaded and
                compliance.clinical_waste_policy_uploaded and
                compliance.sharps_policy_uploaded and
                compliance.staff_training_records_uploaded and
                compliance.transport_license_valid and
                compliance.environmental_permit_valid and
                compliance.data_protection_registration_valid and
                compliance.audit_status == AuditStatusEnum.passed and
                not compliance.is_flagged_noncompliant
)
            if overall_compliant:
                compliant_count += 1

            summaries.append({
                "organization_id": str(org.id),
                "organization_name": org.name,
                "region": getattr(org, "region", "Unknown"),
                "iso_27001_certified": compliance.iso_27001_certified,
                "nhs_dsp_toolkit_complete": compliance.nhs_dsp_toolkit_complete,
                "cyber_essentials_ready": compliance.cyber_essentials_ready,
                "has_waste_license": compliance.has_waste_license,
                "gdpr_policy_uploaded": compliance.gdpr_policy_uploaded,
                "clinical_waste_policy_uploaded": compliance.clinical_waste_policy_uploaded,
                "sharps_policy_uploaded": compliance.sharps_policy_uploaded,
                "staff_training_records_uploaded": compliance.staff_training_records_uploaded,
                "transport_license_valid": compliance.transport_license_valid,
                "environmental_permit_valid": compliance.environmental_permit_valid,
                "data_protection_registration_valid": compliance.data_protection_registration_valid,
                "audit_status": compliance.audit_status.value,
                "last_audit_date": compliance.last_audit_date.strftime("%Y-%m-%d") if compliance.last_audit_date else None,
                "overall_compliant": overall_compliant,
                "last_checked": compliance.created_at.strftime("%Y-%m-%d")
})

    total = len(organizations)
    non_compliant = total - compliant_count
    rate = f"{round((compliant_count / total) * 100)}%" if total > 0 else "N/A"

    log_activity(
        db=db,
        user_id=current_user.id,
        org_id=None,
        action="regulatory_compliance_summary_viewed",
        details=f"Regulatory user {current_user.name} viewed full compliance summary"
    )

    # ✅ Handle Export
    if export == "csv":
        csv_data = generate_csv(summaries)
        return StreamingResponse(csv_data, media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=compliance_summary.csv"
        })

    elif export == "pdf":
        pdf_data = generate_pdf(summaries)
        return StreamingResponse(pdf_data, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=compliance_summary.pdf"
        })

    # ✅ If requesting charts
    chart = None
    if include_charts:
        chart = generate_compliance_chart(summaries)

    return {
        "total_organizations": total,
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant,
        "compliance_rate": rate,
        "organization_summaries": summaries,
        "chart": "Included as PNG binary stream" if include_charts else None
    }