# app/utils/qr_utils.py

import qrcode
import io
import base64

def generate_qr_code_base64(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()

    qr_base64 = base64.b64encode(img_bytes).decode("utf-8")
    return qr_base64