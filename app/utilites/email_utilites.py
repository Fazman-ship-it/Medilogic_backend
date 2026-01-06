# app/utils/email_utils.py
# app/utils/email_utils.py
import os
import re
from typing import Optional, List, Dict, Any

from mailjet_rest import Client
from dotenv import load_dotenv

load_dotenv()

MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "notifications@medilogicglobal.co.uk")
EMAIL_FROM_NAME = "MedilogicGlobal"

# ✅ Simple regex for email validation
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: Optional[List[Dict[str, Any]]] = None
):
    # --- Validate recipient email ---
    if not to_email or not EMAIL_REGEX.match(to_email.strip()):
        print(f"❌ Invalid or empty recipient email provided: '{to_email}'")
        return  # stop execution, don’t try to send

    # --- Validate attachments (optional) ---
    safe_attachments = []
    if attachments:
        if not isinstance(attachments, list):
            print("❌ attachments must be a list of dicts. Ignoring attachments.")
            attachments = None
        else:
            for i, att in enumerate(attachments):
                if not isinstance(att, dict):
                    print(f"❌ Attachment #{i} is not a dict. Skipping.")
                    continue

                # Must match Mailjet expected keys
                ct = att.get("ContentType")
                fn = att.get("Filename")
                b64 = att.get("Base64Content")

                if not ct or not fn or not b64:
                    print(f"❌ Attachment #{i} missing ContentType/Filename/Base64Content. Skipping.")
                    continue

                safe_attachments.append({
                    "ContentType": ct,
                    "Filename": fn,
                    "Base64Content": b64
                })

    try:
        mailjet = Client(auth=(MAILJET_API_KEY, MAILJET_SECRET_KEY), version='v3.1')

        message = {
            "From": {
                "Email": EMAIL_FROM,
                "Name": EMAIL_FROM_NAME
            },
            "To": [
                {
                    "Email": to_email,
                    "Name": "User"
                }
            ],
            "Subject": subject,
            "TextPart": body,
            "HTMLPart": f"<p>{body}</p>",
        }

        # ✅ Only include attachments if valid ones exist
        if safe_attachments:
            message["Attachments"] = safe_attachments

        data = {"Messages": [message]}

        result = mailjet.send.create(data=data)

        if 200 <= result.status_code < 300:
            print(f"📧 Email sent to {to_email} | attachments={len(safe_attachments)}")
        else:
            print(f"❌ Failed to send email to {to_email}: {result.json()}")

    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")