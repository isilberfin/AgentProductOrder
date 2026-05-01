# AgentMail

An AI-powered order management and customer support system built as a portfolio project. It monitors orders in real time, sends LLM-generated emails on key events, and provides a RAG-based support chat.

## Architecture

```
Streamlit UI  ->  FastAPI  ->  RabbitMQ  ->  Worker (Consumer)
                     |                              |
                  SQLite                   LangGraph (chat)
                                           Pinecone (RAG)
                                           Cloudflare R2 (storage)
                                           Brevo API (email)
```

## Order Flow

```
User enters name & email and places order
    |
    |-- "I received the product" clicked before 30s
    |       -> timer cancelled, order marked as delivered
    |       -> review form shown (optional)
    |
    |-- Cancelled via chat before 30s
    |       -> order cancelled -> thank you screen
    |
    |-- 30 seconds pass with no action
            -> delay apology email sent (LLM-generated)
            -> "I received the product" still available
            -> cancellation via chat still available
            -> 5 minutes after delay: order auto-delivered
            -> review form shown (optional)

Review (optional):
    |-- Skip -> thank you email sent -> thank you screen
    |-- Submit -> GPT-4o sentiment analysis
            |-- positive -> thank you email sent -> thank you screen
            |-- neutral  -> thank you email sent -> thank you screen
            |-- negative -> apology email sent (references complaint,
                            acknowledges delay if applicable) -> thank you screen
```

## Project Structure

```
agent-mail/
├── api/
│   └── main.py               # FastAPI endpoints
├── worker/
│   ├── consumer.py           # RabbitMQ listener, timer logic, email triggers
│   ├── chat_graph.py         # LangGraph: politeness filter -> classify -> RAG -> answer
│   ├── rag.py                # Pinecone retrieval (products + order procedures)
│   ├── mailer.py             # Brevo API email sender
│   └── r2.py                 # Cloudflare R2 file fetcher
├── state/
│   └── store.py              # SQLite order state
├── ui/
│   └── app.py                # Streamlit frontend
├── config.py                 # Centralized env loading
├── docker-compose.yml        # RabbitMQ
├── .env.example
└── requirements.txt
```

## Chat Graph

Customer messages are routed through a LangGraph pipeline:

- **Politeness Filter** — keyword list loaded from Cloudflare R2 `bad-words.txt`; if matched, GPT-4o evaluates full message context to confirm; returns kindness message if inappropriate
- **classify** — GPT-4o classifies message as product, order, or unrelated; conditional edge routes to the correct answer node
- **answer_product** — retrieves from Pinecone products namespace, answers with RAG context
- **answer_order** — retrieves from Pinecone order-procedures namespace, combines with live order status; if cancel intent detected, returns `__CANCEL__` and order is cancelled
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
BREVO_API_KEY=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ACCOUNT_ID=...
R2_BUCKET=...
```

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

On first worker startup, source docs are fetched from Cloudflare R2 and automatically embedded and indexed into Pinecone. Subsequent startups skip indexing unless the content has changed.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Place an order |
| POST | `/orders/{id}/deliver` | Mark order as delivered |
| POST | `/orders/{id}/review` | Submit a review |
| POST | `/orders/{id}/cancel` | Cancel an order |
| GET | `/orders/{id}` | Get order state |
| GET | `/orders` | List all orders |
| POST | `/orders/{id}/chat` | Send a chat message (post-order) |
| POST | `/chat` | Send a chat message (pre-order, product questions) |
