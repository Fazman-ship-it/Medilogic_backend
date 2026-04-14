# app/utils/user_onboarding.py

from app.utilites.email_utilites import send_email

def send_welcome_email(
    to_email: str,
    full_name: str,
    role: str,
    temp_password: str,
    login_link: str = "https://www.medilogicglobal.co.uk/login"
):

    print(f"📨 DEBUG: send_welcome_email() called with to_email={to_email}")

    if not to_email or "@" not in to_email:
        print(f"❌ Invalid email received in send_welcome_email: {to_email}")
        return     
    subject = f"Welcome to Medilogic as {role.capitalize()}"

    # Build the email body as HTML with styling
    body = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, Helvetica, sans-serif;
                background-color: #f7f9fc;
                color: #333333;
                line-height: 1.6;
                padding: 20px;
            }}
            .container {{
                background-color: #ffffff;
                border-radius: 8px;
                padding: 30px;
                max-width: 600px;
                margin: auto;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }}
            h2 {{
                color: #004085;
            }}
            ul {{
                background-color: #f1f4f9;
                padding: 15px;
                border-radius: 6px;
                list-style-type: none;
            }}
            ul li {{
                margin: 8px 0;
            }}
            .button {{
                display: inline-block;
                background-color: #007bff;
                color: #ffffff !important;
                padding: 12px 20px;
                border-radius: 6px;
                text-decoration: none;
                font-weight: bold;
            }}
            .footer {{
                margin-top: 30px;
                font-size: 12px;
                color: #6c757d;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to Medilogic 🎉</h2>
            <p>Dear {full_name},</p>
            <p>
                We are pleased to inform you that you have been successfully onboarded 
                as a <strong>{role.capitalize()}</strong> on the Medilogic platform.
            </p>

            <p><strong>Your temporary login credentials:</strong></p>
            <ul>
                <li><strong>Temporary Password:</strong> {temp_password}</li>
            </ul>

            <p>
                You can log in using the button below:
            </p>
            <p>
                <a href="{login_link}" class="button">Log in to Medilogic</a>
            </p>

            <p>
                For your convenience, all organization details and invite codes can be 
                securely accessed from your Medilogic dashboard after logging in.
            </p>

            <p>
                <em>Please ensure you change your password immediately after your first login 
                for security purposes.</em>
            </p>

            <br>
            <p>Best regards,</p>
            <p><strong>The Medilogic Team</strong></p>

            <div class="footer">
                <p>
                    This is an automated message. Please do not reply directly to this email.<br>
                    &copy; {2025} Medilogic. All rights reserved.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    send_email(to_email=to_email, subject=subject, body=body)