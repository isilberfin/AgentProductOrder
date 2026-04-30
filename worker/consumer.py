import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pika
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import RABBITMQ_URL, OPENAI_API_KEY
from state.store import get_order, update_order, log_email
from worker.mailer import send_email

QUEUE         = "order_events"
DELAY_SECONDS = 60

llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=512)

_timers: dict[str, threading.Timer] = {}


# ── helpers ────────────────────────────────────────────────────────────────────

def _llm_email(prompt: str) -> tuple[str, str]:
    """Call LLM with prompt, return (subject, body)."""
    response = llm.invoke([HumanMessage(content=prompt)])
    lines = response.content.strip().split("\n", 1)
    subject = lines[0].replace("Subject:", "").strip()
    body = lines[1].strip() if len(lines) > 1 else response.content
    return subject, body


def _classify_sentiment(review_text: str) -> str:
    response = llm.invoke([HumanMessage(content=(
        f"Classify the sentiment of this customer review.\n"
        f"Review: \"{review_text}\"\n\n"
        "Reply with one word only: NEGATIVE or POSITIVE."
    ))])
    raw = response.content.strip().upper()
    return "NEGATIVE" if "NEGATIVE" in raw else "POSITIVE"


# ── event handlers ─────────────────────────────────────────────────────────────

def _on_timeout(order_id: str):
    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return
    print(f"\n⏰  [{order_id[:8]}] 1 minute passed — sending delay apology")
    if order["apology_sent"]:
        return
    subject, body = _llm_email(
        "Write a short sincere apology email for a delayed order. "
        "Subject line first, then body. 3-4 sentences max. "
        "Sign as 'AgentMail Team'."
    )
    send_email(order["email"], subject, body, "delay_apology")
    update_order(order_id, apology_sent=1, status="delayed",
                 delayed_at=datetime.now(timezone.utc).isoformat())
    log_email(order_id, "delay_apology")


def _on_delivered(order_id: str):
    if order_id in _timers:
        _timers.pop(order_id).cancel()
    order = get_order(order_id)
    if not order:
        return
    send_thankyou = order["status"] == "pending" and not order["apology_sent"]
    update_order(order_id, delivered_at=datetime.now(timezone.utc).isoformat(),
                 status="delivered")
    if send_thankyou:
        subject, body = _llm_email(
            "Write a short, warm order confirmation email. "
            "Subject line first, then body. 3-4 sentences max. "
            "Sign as 'AgentMail Team'."
        )
        send_email(order["email"], subject, body, "thank_you")
        update_order(order_id, thankyou_sent=1)
        log_email(order_id, "thank_you")


def _on_review(order_id: str, review_text: str):
    order = get_order(order_id)
    if not order:
        return
    sentiment = _classify_sentiment(review_text)
    update_order(order_id, review_text=review_text)
    if sentiment == "NEGATIVE":
        tone = (
            "The customer already received a delay apology. Acknowledge this and offer extra support."
            if order["apology_sent"] else
            "Write a sincere apology for a bad experience."
        )
        subject, body = _llm_email(
            f"{tone} Review: '{review_text}'. "
            "Subject line first, then body. 3-4 sentences. "
            "Sign as 'AgentMail Team'."
        )
        send_email(order["email"], subject, body, "review_apology")
        log_email(order_id, "review_apology")


# ── RabbitMQ consumer ──────────────────────────────────────────────────────────

def handle_message(ch, method, properties, body):
    msg      = json.loads(body)
    event    = msg["event"]
    order_id = msg["order_id"]

    print(f"\n📨  Event received: {event.upper()} | order={order_id[:8]}")

    if event == "order_created":
        t = threading.Timer(DELAY_SECONDS, _on_timeout, args=[order_id])
        t.daemon = True
        t.start()
        _timers[order_id] = t

    elif event == "order_delivered":
        _on_delivered(order_id)

    elif event == "review_submitted":
        _on_review(order_id, msg.get("review_text", ""))

    ch.basic_ack(delivery_tag=method.delivery_tag)


def start():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE, on_message_callback=handle_message)
    print("🐇  Worker listening on RabbitMQ...")
    channel.start_consuming()


if __name__ == "__main__":
    start()
