import io
import sys
from pathlib import Path

import boto3
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, R2_BUCKET


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def fetch_text(filename: str) -> str:
    """Fetch a file from R2 and return its content as a string."""
    buf = io.BytesIO()
    _client().download_fileobj(R2_BUCKET, filename, buf)
    return buf.getvalue().decode("utf-8")


def fetch_bytes(filename: str) -> bytes:
    """Fetch a file from R2 and return its raw bytes."""
    buf = io.BytesIO()
    _client().download_fileobj(R2_BUCKET, filename, buf)
    return buf.getvalue()
