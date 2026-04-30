# AgentMail

An AI-powered order management and customer support system built as a portfolio project. It monitors orders in real time, sends LLM-generated emails on key events, and provides a RAG-based support chat.

## Architecture

```
Streamlit UI  ->  FastAPI  ->  RabbitMQ  ->  Worker (Consumer)
                     |                              |
                  SQLite                   LangGraph (chat)
                                           Pinecone (RAG)
                                           Gmail (email)
```

## Order Flow

```
User enters email and places order
    |
    |-- "I received the product" clicked before 1 min
    |       -> thank you email sent
    |       -> review form shown (optional)
    |
    |-- 1 minute passes with no action
            -> delay apology email sent
            -> "I received the product" still available
            -> 5 minutes after delay: order auto-delivered
            -> review form shown (optional)

Review (optional):
    |-- Skip -> thank you screen
    |-- Submit -> GPT-4o sentiment analysis
            |-- positive -> thank you screen
            |-- negative -> apology email sent -> thank you screen
```

## Project Structure

```
agent-mail/
├── api/
│   └── main.py               # FastAPI endpoints
├── worker/
│   ├── consumer.py           # RabbitMQ listener, timer logic, email triggers
│   ├── chat_graph.py         # LangGraph: classify -> RAG -> answer
│   ├── rag.py                # Pinecone retrieval (products + order procedures)
│   └── mailer.py             # Gmail SMTP sender
├── state/
│   └── store.py              # SQLite order state
├── data/
│   ├── products.json         # Product catalog
│   └── order_procedures.json # FAQ for order procedure RAG
├── ui/
│   └── app.py                # Streamlit frontend
├── config.py                 # Centralized env loading
├── docker-compose.yml        # RabbitMQ
├── .env.example
└── requirements.txt
```

## Chat Graph

Customer messages are routed through a LangGraph pipeline:

- **classify** — GPT-4o classifies message as product, order, or unrelated
- **answer_product** — retrieves from Pinecone products namespace, answers with RAG
- **answer_order** — retrieves from Pinecone order-procedures namespace, combines with live order status
- **answer_unrelated** — politely redirects to order or product topics

## Setup

Requirements: Python 3.11+, Docker Desktop

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
```

Fill in `.env`:

```
OPENAI_API_KEY=...
PINECONE_API_KEY=...
PINECONE_INDEX=agentmail-products
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
RABBITMQ_URL=amqp://guest:guest@localhost/
MAIL_SENDER=your@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

`MAIL_PASSWORD` is a Gmail App Password (not your account password). Generate one at Google Account > Security > App Passwords.

**3. Start RabbitMQ**

```bash
docker-compose up -d
```

## Running

Open 3 terminals:

```bash
# Terminal 1 - API
uvicorn api.main:app --reload

# Terminal 2 - Worker (also indexes Pinecone on first run)
python -m worker.consumer

# Terminal 3 - UI
streamlit run ui/app.py
```

UI: http://localhost:8501  
RabbitMQ dashboard: http://localhost:15672 (guest / guest)

On first worker startup, products and order procedures are automatically embedded and indexed into Pinecone. Subsequent startups skip indexing.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Place an order |
| POST | `/orders/{id}/deliver` | Mark order as delivered |
| POST | `/orders/{id}/review` | Submit a review |
| GET | `/orders/{id}` | Get order state |
| GET | `/orders` | List all orders |
| POST | `/orders/{id}/chat` | Send a chat message |
