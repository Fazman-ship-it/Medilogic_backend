# app/utils/mailer.py

from app.utilites.email_utilites import send_email  # reuse your base function

def send_applicant_approved_email(to_email: str, full_name: str, temp_password: str, login_link: str):
    subject = "Medilogic International Application – Approval Notification"
    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #2E86C1;">Application Approved</h2>
        <p>Dear {full_name},</p>

        <p>We are pleased to inform you that your <strong>international application</strong> with 
        <span style="color:#2E86C1;"><b>Medilogic</b></span> has been <strong>successfully approved</strong>.</p>

        <p>You can now access your Medilogic account using the temporary login details provided below:</p>

        <div style="margin: 20px 0; padding: 15px; background-color: #f4f6f9; border-left: 4px solid #2E86C1;">
          <p><b>Temporary Password:</b> <span style="color:#C0392B;">{temp_password}</span></p>
          <p><b>Login Portal:</b> <a href="{login_link}" style="color:#2E86C1;">{login_link}</a></p>
        </div>

        <p><b>Important:</b> For security purposes, please change your password immediately after your first login.</p>

        <p>If you experience any issues accessing your account, please contact our support team at 
        <a href="mailto:support@medilogic.com">support@medilogic.com</a>.</p>

        <br>
        <p>Thank you for choosing Medilogic. We look forward to supporting your journey.</p>

        <p style="margin-top: 30px;">
          Kind regards,<br>
          <b>The Medilogic Team</b>
        </p>
      </body>
    </html>
    """
    send_email(to_email, subject, body)