import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from config import BREVO_API_KEY, MAIL_SENDER


def send_email(to: str, subject: str, body: str, email_type: str):
    requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "sender": {"email": MAIL_SENDER},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
    )
    print(f"\n✉️  [{email_type.upper()}] sent to {to} | Subject: {subject}")
