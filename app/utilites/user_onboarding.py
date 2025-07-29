# app/utils/user_onboarding.py

from app.utilites import send_email  # assuming this is your generic email sender

def send_welcome_email(
    to_email: str,
    full_name: str,
    role: str,
    temp_password: str,
    organization_id: str = None,
    invite_code: str = None,
    login_link: str = "https://medilogic.vercel.app/login"
):
    subject = f"Welcome to Medilogic as {role.capitalize()}"

    # Build the email body as HTML
    body = f"""
    <html>
    <body>
        <h2>Welcome to Medilogic 🎉</h2>
        <p>Dear {full_name},</p>
        <p>You have been onboarded as a <strong>{role.capitalize()}</strong> on the Medilogic platform.</p>
    """

    if organization_id and invite_code:
        body += f"""
        <p>Here are your credentials:</p>
        <ul>
            <li><strong>Organization ID:</strong> {organization_id}</li>
            <li><strong>Invite Code:</strong> {invite_code}</li>
        </ul>
        """

    body += f"""
        <ul>
            <li><strong>Temporary Password:</strong> {temp_password}</li>
        </ul>
        <p>Please log in here: <a href="{login_link}">{login_link}</a></p>
        <p>After logging in, please change your password immediately.</p>
        <br>
        <p>Best regards,<br>Medilogic Team</p>
    </body>
    </html>
    """

    send_email(to_email=to_email, subject=subject, body=body)