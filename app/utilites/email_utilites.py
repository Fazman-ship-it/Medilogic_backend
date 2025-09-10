# app/utils/email_utils.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re
from dotenv import load_dotenv

load_dotenv()

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT"))  # should be 465 for SSL
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# ✅ Simple regex for email validation
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def send_email(to_email: str, subject: str, body: str):
    # --- Validate recipient email ---
    if not to_email or not EMAIL_REGEX.match(to_email.strip()):
        print(f"❌ Invalid or empty recipient email provided: '{to_email}'")
        return  # stop execution, don’t try to send

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "html"))

    try:
        # ✅ Use SMTP_SSL instead of SMTP + starttls
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as server:
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, msg.as_string())
            print(f"📧 Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")