# app/utils/qr_utils.py

import qrcode
import io
import base64

def generate_qr_code_base64(
    data: str,
    version: int = 1,
    box_size: int = 10,
    border: int = 4,
    error_correction=qrcode.constants.ERROR_CORRECT_M
) -> str:
    qr = qrcode.QRCode(version=version, box_size=box_size, border=border, error_correction=error_correction)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")