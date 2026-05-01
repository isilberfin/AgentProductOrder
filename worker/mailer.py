import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAIL_SENDER, MAIL_PASSWORD


def send_email(to: str, subject: str, body: str, email_type: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = MAIL_SENDER
    msg["To"] = to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(MAIL_SENDER, MAIL_PASSWORD)
            smtp.sendmail(MAIL_SENDER, to, msg.as_string())
        print(f"\n✉️  [{email_type.upper()}] sent to {to} | Subject: {subject}")
    except Exception as e:
        print(f"\n❌  [{email_type.upper()}] FAILED to {to} | {e}")
