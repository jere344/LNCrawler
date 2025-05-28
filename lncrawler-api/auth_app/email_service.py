import requests
from django.conf import settings
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

class BrevoEmailService:
    def __init__(self):
        self.api_key = settings.BREVO_API_KEY
        self.sender_email = settings.DEFAULT_FROM_EMAIL
        self.sender_name = settings.EMAIL_SENDER_NAME
        self.base_url = 'https://api.brevo.com/v3'

    def send_password_reset_email(self, user_email, username, reset_token):
        """Send password reset email using Brevo API"""
        if not self.api_key:
            logger.error("Brevo API key not configured")
            return False

        reset_url = f"{settings.SITE_URL}/reset-password?token={reset_token}"
        
        # Email content
        subject = "Password Reset Request - LN Crawler"
        html_content = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hello {username},</p>
            <p>You have requested to reset your password. Click the link below to reset your password:</p>
            <p><a href="{reset_url}" style="background-color: #4CAF50; color: white; padding: 14px 25px; text-decoration: none; border-radius: 4px;">Reset Password</a></p>
            <p>If the button doesn't work, copy and paste this URL into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 24 hours.</p>
            <p>If you didn't request this password reset, please ignore this email.</p>
            <br>
            <p>Best regards,<br>LN Crawler Team</p>
        </body>
        </html>
        """

        text_content = f"""
        Password Reset Request

        Hello {username},

        You have requested to reset your password. Copy and paste this URL into your browser to reset your password:

        {reset_url}

        This link will expire in 24 hours.

        If you didn't request this password reset, please ignore this email.

        Best regards,
        LN Crawler Team
        """

        payload = {
            "sender": {
                "name": self.sender_name,
                "email": self.sender_email
            },
            "to": [
                {
                    "email": user_email,
                    "name": username
                }
            ],
            "subject": subject,
            "htmlContent": html_content,
            "textContent": text_content
        }

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'api-key': self.api_key
        }

        try:
            response = requests.post(
                f"{self.base_url}/smtp/email",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 201:
                logger.info(f"Password reset email sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

email_service = BrevoEmailService()
