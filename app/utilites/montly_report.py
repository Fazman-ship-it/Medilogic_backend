import io
import csv
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from fpdf import FPDF
from app.models import Trip, DeliveryConfirmation
from app.utilites.storage_utilites import generate_presigned_url_async
from app.utilites.email_utilites import send_email

# --- Custom PDF class with footer ---
class WasteStatementPDF(FPDF):
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        # Add centered footer text
        self.cell(0, 10, "Powered by Medilogic Platform", 0, 0, "C")

async def generate_monthly_waste_statement(db: Session, year: int, month: int):
    """
    Generate monthly waste statement CSV and PDF for all trips with delivery confirmations.
    Sends emails to both internal and external clients.
    Includes organization name, driver name, and Medilogic branding.
    """

    # --- Define date range for the month ---
    start_date = datetime(year, month, 1)
    end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    # --- Query trips with delivery confirmations in the given month ---
    trips = (
        db.query(Trip)
        .join(DeliveryConfirmation, DeliveryConfirmation.trip_id == Trip.id)
        .filter(
            DeliveryConfirmation.dropoff_at >= start_date,
            DeliveryConfirmation.dropoff_at < end_date
        )
        .all()
    )

    if not trips:
        return  # No trips for this month

    # --- Sort trips chronologically ---
    trips.sort(key=lambda t: t.delivery_confirmation.dropoff_at or t.delivery_confirmation.pickup_at)

    # --- Prepare CSV ---
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)

    # Branding rows
    org_name_heading = trips[0].organization.name if hasattr(trips[0].organization, 'name') else "Organization"
    csv_writer.writerow([f"{org_name_heading} - Monthly Waste Statement - {start_date.strftime('%B %Y')}"])
    csv_writer.writerow(["Generated via Medilogic Platform"])
    csv_writer.writerow([])  # Empty row

    csv_writer.writerow([
        "Trip ID", "Organization Name", "Driver Name",
        "Client Name", "Client Email", "Client Signature",
        "Pickup Timestamp", "Pickup Photo", "Dropoff Timestamp",
        "WTN Code", "Dropoff Facility Name", "Dropoff Facility Address",
        "Dropoff Facility Signature", "Dropoff Photo",
        "Extra Notes", "Cost"
    ])

    # --- Prepare PDF ---
    pdf = WasteStatementPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Add Medilogic logo
    try:
        pdf.image("app/static/medilogic_logo.png", x=10, y=8, w=33)
        pdf.ln(15)
    except Exception:
        pdf.ln(15)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"{org_name_heading} - Monthly Waste Statement - {start_date.strftime('%B %Y')}", ln=True, align="C")
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Generated via Medilogic Platform", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", size=10)

    for trip in trips:
        conf = trip.delivery_confirmation  # assuming one-to-one

        # Organization name
        organization_name = trip.organization.name if hasattr(trip.organization, "name") else "N/A"

        # Client info
        client_name = conf.external_client_name or trip.client_name
        client_email = conf.external_client_email or trip.client_email

        # Driver name
        driver_name = trip.driver_name

        # Cost
        trip_cost = trip.cost if trip.cost is not None else "N/A"

        # Presigned URLs
        pickup_photo_url = await generate_presigned_url_async(conf.pickup_photo_path) if conf.pickup_photo_path else ""
        dropoff_photo_url = await generate_presigned_url_async(conf.dropoff_photo_path) if conf.dropoff_photo_path else ""
        client_signature_url = await generate_presigned_url_async(conf.signature_image_path) if conf.signature_image_path else ""
        facility_signature_url = await generate_presigned_url_async(conf.disposal_facility_signature_path) if conf.disposal_facility_signature_path else ""

        # --- CSV row ---
        csv_writer.writerow([
            str(trip.id),
            organization_name,
            driver_name,
            client_name,
            client_email,
            client_signature_url,
            conf.pickup_at,
            pickup_photo_url,
            conf.dropoff_at,
            conf.wtn_code,
            conf.disposal_facility_name,
            conf.disposal_facility_address,
            facility_signature_url,
            dropoff_photo_url,
            conf.extra_notes,
            trip_cost
        ])

        # --- PDF content with clickable links ---
        pdf.multi_cell(0, 6, f"Trip ID: {trip.id} | Organization: {organization_name}")
        pdf.multi_cell(0, 6, f"Driver: {driver_name}")

        pdf.multi_cell(0, 6, f"Client: {client_name} | Email: {client_email} | Signature: ")
        if client_signature_url:
            pdf.set_text_color(0, 0, 255)
            pdf.cell(0, 6, client_signature_url, ln=True, link=client_signature_url)
            pdf.set_text_color(0, 0, 0)

        pdf.multi_cell(0, 6, f"Pickup: {conf.pickup_at} | Photo: ")
        if pickup_photo_url:
            pdf.set_text_color(0, 0, 255)
            pdf.cell(0, 6, pickup_photo_url, ln=True, link=pickup_photo_url)
            pdf.set_text_color(0, 0, 0)

        pdf.multi_cell(0, 6, f"Dropoff: {conf.dropoff_at} | WTN: {conf.wtn_code}")
        pdf.multi_cell(0, 6, f"Facility: {conf.disposal_facility_name}, {conf.disposal_facility_address} | Signature: ")
        if facility_signature_url:
            pdf.set_text_color(0, 0, 255)
            pdf.cell(0, 6, facility_signature_url, ln=True, link=facility_signature_url)
            pdf.set_text_color(0, 0, 0)

        pdf.multi_cell(0, 6, f"Dropoff Photo: ")
        if dropoff_photo_url:
            pdf.set_text_color(0, 0, 255)
            pdf.cell(0, 6, dropoff_photo_url, ln=True, link=dropoff_photo_url)
            pdf.set_text_color(0, 0, 0)

        pdf.multi_cell(0, 6, f"Notes: {conf.extra_notes} | Cost: {trip_cost}")
        pdf.ln(5)

    # --- Convert CSV and PDF to bytes ---
    csv_bytes = csv_buffer.getvalue().encode()
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    pdf_bytes = pdf_buffer.read()

    attachments = [
        {"ContentType": "text/csv",
         "Filename": f"medilogic_waste_statement_{year}_{month}.csv",
         "Base64Content": csv_bytes.decode("utf-8")},
        {"ContentType": "application/pdf",
         "Filename": f"medilogic_waste_statement_{year}_{month}.pdf",
         "Base64Content": pdf_bytes.decode("latin1")}
    ]

    # --- Send emails ---
    for trip in trips:
        conf = trip.delivery_confirmation
        recipients = set()
        if trip.client_email:
            recipients.add(trip.client_email)
        if conf.external_client_email:
            recipients.add(conf.external_client_email)

        for email in recipients:
            send_email(
                to_email=email,
                subject=f"{organization_name} Waste Statement - {start_date.strftime('%B %Y')}",
                body=f"Please find attached your monthly waste statement for {organization_name}. Generated via Medilogic Platform.",
                attachments=attachments
            )