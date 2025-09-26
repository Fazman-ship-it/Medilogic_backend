# app/utils/email_utils.py
import os
import re
from mailjet_rest import Client
from dotenv import load_dotenv

load_dotenv()

MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "medilogicnotify@gmail.com")
EMAIL_FROM_NAME = "Medilogic"

# ✅ Simple regex for email validation
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def send_email(to_email: str, subject: str, body: str):
    # --- Validate recipient email ---
    if not to_email or not EMAIL_REGEX.match(to_email.strip()):
        print(f"❌ Invalid or empty recipient email provided: '{to_email}'")
        return  # stop execution, don’t try to send

    try:
        mailjet = Client(auth=(MAILJET_API_KEY, MAILJET_SECRET_KEY), version='v3.1')
        data = {
            'Messages': [
                {
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
                    "HTMLPart": f"<p>{body}</p>"
                }
            ]
        }
        result = mailjet.send.create(data=data)
        if 200 <= result.status_code < 300:
            print(f"📧 Email sent to {to_email}")
        else:
            print(f"❌ Failed to send email to {to_email}: {result.json()}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")