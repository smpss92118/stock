import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import sys

# Add project root to path to import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
try:
    import config
except ImportError:
    # Fallback if run directly or path issue
    config = None

def send_email(subject, body, attachment_paths=[]):
    """
    Send an email with optional attachments using Gmail SMTP.
    """
    sender_email = config.EMAIL_SENDER if config else "smpss92118smpss92118@gmail.com"
    receiver_email = config.EMAIL_RECEIVER if config else "smpss92118smpss92118@gmail.com"
    password = config.EMAIL_PASSWORD if config else os.environ.get("GMAIL_APP_PASSWORD")

    if not password or password == "YOUR_APP_PASSWORD_HERE":
        print("❌ Error: Email password not set. Please set GMAIL_APP_PASSWORD in config.py or env var.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    for file_path in attachment_paths:
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                # After the file is closed
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                msg.attach(part)
            except Exception as e:
                print(f"⚠️ Failed to attach {file_path}: {e}")
        else:
            print(f"⚠️ Attachment not found: {file_path}")

    try:
        print(f"Sending email to {receiver_email}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
        print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

if __name__ == "__main__":
    # Test
    send_email("Test Subject", "This is a test email from Stock Bot.")
