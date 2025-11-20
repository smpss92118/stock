import os

# --- Email Configuration ---
# Please set your Gmail App Password here or in environment variable 'GMAIL_APP_PASSWORD'
# To generate App Password: Go to Google Account -> Security -> 2-Step Verification -> App passwords
EMAIL_SENDER = "smpss92118smpss92118@gmail.com"
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
EMAIL_RECEIVER = "smpss92118smpss92118@gmail.com"

# --- System Paths ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, 'scripts')
