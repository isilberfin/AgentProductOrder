import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import resend
from config import RESEND_API_KEY, MAIL_SENDER

resend.api_key = RESEND_API_KEY


def send_email(to: str, subject: str, body: str, email_type: str):
    resend.Emails.send({
        "from": MAIL_SENDER,
        "to": to,
        "subject": subject,
        "text": body,
    })
    print(f"\n✉️  [{email_type.upper()}] sent to {to} | Subject: {subject}")
