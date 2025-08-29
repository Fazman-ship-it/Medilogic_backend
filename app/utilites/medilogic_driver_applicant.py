from app.utilites.email_utilites import send_email  # ✅ assuming you already have a generic send_email utility

def send_driver_welcome_email(to_email: str, full_name: str, temp_password: str, login_link: str):
    subject = "Medilogic Driver – Approval & Welcome"
    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #27AE60;">Welcome to Medilogic!</h2>
        <p>Dear {full_name},</p>

        <p>Congratulations! 🎉 Your <strong>driver application</strong> with 
        <span style="color:#27AE60;"><b>Medilogic</b></span> has been <strong>approved</strong>.</p>

        <p>You can now access your Medilogic Driver account using the temporary login details below:</p>

        <div style="margin: 20px 0; padding: 15px; background-color: #f4f6f9; border-left: 4px solid #27AE60;">
          <p><b>Temporary Password:</b> <span style="color:#C0392B;">{temp_password}</span></p>
          <p><b>Login Portal:</b> <a href="{login_link}" style="color:#27AE60;">{login_link}</a></p>
        </div>

        <p><b>Next Steps:</b></p>
        <ul>
          <li>Login with your temporary password.</li>
          <li>Immediately update your password for security.</li>
          <li>Ensure all your required documents are uploaded and verified.</li>
        </ul>

        <p>If you face any issues, kindly contact our support team at 
        <a href="mailto:support@medilogic.com">support@medilogic.com</a>.</p>

        <br>
        <p>We’re excited to have you on board! 🚚💚</p>

        <p style="margin-top: 30px;">
          Kind regards,<br>
          <b>The Medilogic Team</b>
        </p>
      </body>
    </html>
    """
    send_email(to_email, subject, body)