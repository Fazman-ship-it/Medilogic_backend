from fpdf import FPDF
import os
import uuid

def generate_confirmation_pdf(confirmation):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Delivery Confirmation Receipt", ln=True, align="C")
    pdf.ln(10)

    pdf.cell(200, 10, txt=f"Trip ID: {confirmation.trip_id}", ln=True)
    pdf.cell(200, 10, txt=f"Confirmed At: {confirmation.confirmed_at}", ln=True)
    pdf.cell(200, 10, txt=f"WTN Code: {confirmation.wtn_code}", ln=True)
    pdf.cell(200, 10, txt=f"IP Address: {confirmation.ip_address}", ln=True)
    pdf.cell(200, 10, txt=f"User-Agent: {confirmation.user_agent}", ln=True)

    output_dir = "static/receipts"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}_receipt.pdf"
    file_path = os.path.join(output_dir, filename)

    pdf.output(file_path)
    return file_path