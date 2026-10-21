"""
SMTP connectivity test script.

Purpose:
Verifies that the system can authenticate with the configured mail server 
and successfully transmit a test message.
"""
from digest.sender import send_email
from config import RECEIVER_EMAIL

def main():
    if not RECEIVER_EMAIL:
        raise ValueError("RECEIVER_EMAIL is missing from environment variables")

    subject = "Test Email - Tendermatch"
    body = """
    If you're reading this, email is working.

    System is alive.
    """

    send_email(subject, body, RECEIVER_EMAIL)
    print("Test email sent.")


if __name__ == "__main__":
    main()
