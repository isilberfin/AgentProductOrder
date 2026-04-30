import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAIL_SENDER, MAIL_PASSWORD


def send_email(to: str, subject: str, body: str, email_type: str):
    msg = MIMEMultipart()
    msg["From"]    = MAIL_SENDER
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(MAIL_SENDER, MAIL_PASSWORD)
        server.sendmail(MAIL_SENDER, to, msg.as_string())

    print(f"\n✉️  [{email_type.upper()}] sent to {to} | Subject: {subject}")
