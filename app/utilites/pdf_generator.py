# app/utils/pdf_generator.py

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
import os
from app.utilites.time_utilities import now_utc,to_local,to_utc  # ✅ Import your new global utilities

def generate_pod_pdf(pod, filename):
    # ✅ Create tenant-specific folder path
    org_id = pod.driver.organization_id
    folder_path = os.path.join("app", "uploads", "pods", f"org_{org_id}")
    os.makedirs(folder_path, exist_ok=True)

    # ✅ Full path
    path = os.path.join(folder_path, filename)

    # ✅ Get the organization timezone (fallback to Africa/Lagos)
    org_timezone = getattr(pod.driver.organization, "timezone", "Africa/Lagos")

    # ✅ Convert timestamp to both UTC and local
    utc_dt = to_utc(pod.timestamp, tz_name=org_timezone)
    local_dt = to_local(utc_dt, tz_name=org_timezone)

    # Format the timestamps
    utc_time = utc_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    local_time = local_dt.strftime(f"%Y-%m-%d %H:%M:%S %Z")  # e.g. BST, WAT, EST

    # ✅ Start PDF
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # --- HEADER ---
    c.setFillColor(colors.HexColor("#003366"))
    c.rect(0, height - 80, width, 80, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(1 * inch, height - 50, "Proof of Delivery")

    # --- BODY CONTENT ---
    c.setFillColor(colors.black)
    y = height - 120
    line_height = 20

    def line(label, value):
        nonlocal y
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y, f"{label}:")
        c.setFont("Helvetica", 12)
        c.drawString(2.8 * inch, y, str(value))
        y -= line_height

    line("POD ID", pod.id)
    line("Trip ID", pod.trip_id)
    line("Submitted By", pod.driver.name)
    line("Delivered To", pod.delivered_to)
    line("Timestamp (UTC)", utc_time)
    line("Timestamp (Local)", local_time)
    line("Notes", pod.notes or "None")

    # --- OPTIONAL: Signature block ---
    if pod.signature_path and os.path.exists(pod.signature_path):
        y -= 30
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y, "Signature:")
        c.drawImage(pod.signature_path, 2.8 * inch, y - 40, width=100, height=40, mask='auto')
        y -= 50

    # --- FOOTER ---
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.gray)
    c.drawString(1 * inch, 40, f"Generated automatically by MediLogic | {utc_time}")

    # --- SAVE PDF ---
    c.showPage()
    c.save()

    return path