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
MAIL_SENDER      = os.environ["MAIL_SENDER"]
MAIL_PASSWORD    = os.environ["MAIL_PASSWORD"]
