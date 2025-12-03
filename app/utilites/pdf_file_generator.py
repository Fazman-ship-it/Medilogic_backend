from fpdf import FPDF
import io

def generate_confirmation_pdf(confirmation) -> bytes:
    """
    Generate a Delivery Confirmation PDF in memory and return bytes.
    Suitable for S3 upload.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Header
    pdf.cell(200, 10, txt="Delivery Confirmation Receipt", ln=True, align="C")
    pdf.ln(10)

    # Trip details
    pdf.cell(200, 10, txt=f"Trip ID: {confirmation.trip_id}", ln=True)
    pdf.cell(200, 10, txt=f"Confirmed At: {confirmation.confirmed_at}", ln=True)
    pdf.cell(200, 10, txt=f"WTN Code: {confirmation.wtn_code}", ln=True)
    pdf.cell(200, 10, txt=f"IP Address: {confirmation.ip_address}", ln=True)
    pdf.cell(200, 10, txt=f"User-Agent: {confirmation.user_agent}", ln=True)
    pdf.cell(200, 10, txt=f"Latitude: {confirmation.latitude}", ln=True)
    pdf.cell(200, 10, txt=f"Longitude: {confirmation.longitude}", ln=True)
    pdf.cell(200, 10, txt=f"Pickup At: {confirmation.pickup_at}", ln=True)
    pdf.cell(200, 10, txt=f"Dropoff At: {confirmation.dropoff_at}", ln=True)

    # Optional: Add signature or photo if you want
    # e.g., pdf.image(signature_path, x=10, y=80, w=50)

    # Output to in-memory bytes buffer
    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer.read()