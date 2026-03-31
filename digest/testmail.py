from digest.sender import send_email

subject = "Test Email - Tendermatch"
body = """
If you're reading this, email is working.

System is alive.
"""

send_email(subject, body, "devayushrout@gmail.com")

print("Test email sent.")