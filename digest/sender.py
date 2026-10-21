"""
SMTP delivery service for the tender intelligence pipeline.

Pipeline role:
Handles the physical transmission of the intelligence reports over SMTP. 
Ensures that findings are delivered to the operations team for action.

Key responsibilities:
- Managing SMTP connection and TLS encryption.
- Authenticating with the mail server via environment credentials.
- Handling transmission errors without crashing the main pipeline process.

Inputs:
- Email subject and body.
- Target recipient address.

Notes:
- Uses Google SMTP by default (smtp.gmail.com).
- Requires SENDER_EMAIL and SENDER_PASSWORD to be set in the environment.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import SENDER_EMAIL, SENDER_PASSWORD


def send_email(subject, body, recipient_email):
    """
    Sends a plaintext email via SMTP.

    Args:
        subject (str): Email subject.
        body (str): Plaintext body content.
        recipient_email (str): Destination address.

    Side Effects:
        - Establishes a socket connection to the SMTP server.
        - Transmits the email message.

    Raises:
        ValueError: If SMTP credentials are not found in the environment.
        Exception: If the SMTP transmission fails for any reason.
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        raise ValueError(
            "SENDER_EMAIL or SENDER_PASSWORD is missing from environment variables"
        )

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()

        print("📩 Email sent successfully.")

    except Exception as e:
        print(f"❌ Email failed: {e}")
        raise
