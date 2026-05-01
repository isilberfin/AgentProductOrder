import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY   = os.environ["OPENAI_API_KEY"]
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX   = os.getenv("PINECONE_INDEX", "agentmail-products")
PINECONE_CLOUD   = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION  = os.getenv("PINECONE_REGION", "us-east-1")
RABBITMQ_URL     = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
MAIL_SENDER   = os.environ["MAIL_SENDER"]
MAIL_PASSWORD = os.environ["MAIL_PASSWORD"]

R2_ACCESS_KEY_ID     = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_ACCOUNT_ID        = os.environ["R2_ACCOUNT_ID"]
R2_BUCKET            = os.environ["R2_BUCKET"]

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
