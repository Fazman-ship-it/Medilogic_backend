# app/utils/pdf_generator.py

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def generate_pod_pdf(pod, filename):
    # ✅ Create tenant-specific folder path
    org_id = pod.driver.organization_id  # assuming pod.driver is loaded and has org info
    folder_path = os.path.join("app", "uploads", "pods", f"org_{org_id}")
    os.makedirs(folder_path, exist_ok=True)

    # ✅ Full path with tenant segregation
    path = os.path.join(folder_path, filename)

    c = canvas.Canvas(path, pagesize=A4)
    text = c.beginText(50, 800)

    text.setFont("Helvetica", 12)
    text.textLine("Proof of Delivery")
    text.textLine(f"POD ID: {pod.id}")
    text.textLine(f"Trip ID: {pod.trip_id}")
    text.textLine(f"Submitted By: {pod.driver.name}")
    text.textLine(f"Delivered To: {pod.delivered_to}")
    text.textLine(f"Timestamp: {pod.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    text.textLine(f"Notes: {pod.notes or 'None'}")

    c.drawText(text)
    c.showPage()
    c.save()
    return path