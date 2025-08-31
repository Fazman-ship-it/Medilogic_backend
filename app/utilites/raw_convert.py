# app/utils/file_utils.py
import os
import img2pdf
from app.main import UPLOAD_DIR_RAW, UPLOAD_DIR_PDF  # or define the paths here too

def ensure_pdf_exists(raw_filename: str):
    raw_path = os.path.join(UPLOAD_DIR_RAW, raw_filename)
    pdf_filename = os.path.splitext(raw_filename)[0] + ".pdf"
    pdf_path = os.path.join(UPLOAD_DIR_PDF, pdf_filename)

    if os.path.exists(pdf_path):
        return pdf_filename

    if os.path.exists(raw_path):
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(raw_path))
        return pdf_filename
    return None