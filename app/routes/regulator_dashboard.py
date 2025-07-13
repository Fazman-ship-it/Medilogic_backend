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

@router.get("/regulator")
def get_regulator_dashboard_compliance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "regulator":
        raise HTTPException(status_code=403, detail="Access denied")

    # 🎯 Get organizations under this regulator
    orgs = db.query(Organization).filter(
        Organization.country == current_user.regulated_country,
        Organization.state == current_user.regulated_state,
        Organization.region == current_user.regulated_region,
    ).all()

    # 📋 Collect compliance status for each
    compliance_data = []
    for org in orgs:
        compliance = db.query(ComplianceStatus).filter_by(organization_id=org.id).first()
        compliance_data.append({
            "organization": org.name,
            "iso_27001": compliance.iso_27001_certified if compliance else False,
            "nhs_dsp_toolkit": compliance.nhs_dsp_toolkit_complete if compliance else False,
            "cyber_essentials": compliance.cyber_essentials_ready if compliance else False,
            "has_waste_license": compliance.has_waste_license if compliance else False,
            "last_audit": compliance.last_audit_date.isoformat() if compliance and compliance.last_audit_date else None
        })

    return {
        "total_organizations": len(orgs),
        "compliance_overview": compliance_data
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


@router.get("/summary")
def get_regulator_compliance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔐 Ensure user is a regulator
    if current_user.role != "regulator":
        raise HTTPException(status_code=403, detail="Only regulators can access this")

    # 🌍 Filter organizations under the regulator's scope
    orgs = db.query(Organization).filter(
        Organization.country == current_user.regulated_country,
        Organization.state == current_user.regulated_state,
        Organization.region == current_user.regulated_region
    ).all()

    total_orgs = len(orgs)
    iso_certified = 0
    nhs_completed = 0
    cyber_ready = 0
    waste_licensed = 0

    for org in orgs:
        comp = org.compliance_status
        if comp:
            if comp.iso_27001_certified:
                iso_certified += 1
            if comp.nhs_dsp_toolkit_complete:
                nhs_completed += 1
            if comp.cyber_essentials_ready:
                cyber_ready += 1
            if comp.has_waste_license:
                waste_licensed += 1

    return {
        "total_organizations": total_orgs,
        "iso_27001_certified": iso_certified,
        "nhs_dsp_toolkit_completed": nhs_completed,
        "cyber_essentials_ready": cyber_ready,
        "waste_license_issued": waste_licensed,
        "percentages": {
            "iso_27001_certified": f"{(iso_certified / total_orgs * 100):.2f}%" if total_orgs else "0%",
            "nhs_dsp_toolkit_completed": f"{(nhs_completed / total_orgs * 100):.2f}%" if total_orgs else "0%",
            "cyber_essentials_ready": f"{(cyber_ready / total_orgs * 100):.2f}%" if total_orgs else "0%",
            "waste_license_issued": f"{(waste_licensed / total_orgs * 100):.2f}%" if total_orgs else "0%"
        }
    }


