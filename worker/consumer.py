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
from constants import QUEUE, DELAY_SECONDS
from state.store import get_order, update_order, log_email
from worker.mailer import send_email

llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=512)

_timers: dict[str, threading.Timer] = {}


# shared helpers

def _to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item["text"] if isinstance(item, dict) and "text" in item else str(item)
            for item in content
        )
    return str(content)


def _llm_email(prompt: str) -> tuple[str, str]:
    """Call LLM with prompt, return (subject, body)."""
    response = llm.invoke([HumanMessage(content=prompt)])
    text = _to_str(response.content).strip().replace("**", "").replace("*", "")
    lines = text.split("\n", 1)
    subject = lines[0].replace("Subject:", "").strip()
    body = lines[1].strip() if len(lines) > 1 else text
    return subject, body


def _classify_sentiment(review_text: str) -> str:
    response = llm.invoke([HumanMessage(content=(
        f"Classify the sentiment of this customer review.\n"
        f"Review: \"{review_text}\"\n\n"
        "Reply with one word only: NEGATIVE, NEUTRAL, or POSITIVE."
    ))])
    raw = _to_str(response.content).strip().upper()
    if "NEGATIVE" in raw:
        return "NEGATIVE"
    if "NEUTRAL" in raw:
        return "NEUTRAL"
    return "POSITIVE"


# event handlers for each order event type

def _on_timeout(order_id: str):
    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return
    print(f"\n⏰  [{order_id[:8]}] 30 seconds passed — sending delay apology")
    if order["apology_sent"]:
        return
    update_order(order_id, apology_sent=1, status="delayed",
                 delayed_at=datetime.now(timezone.utc).isoformat())
    subject, body = _llm_email(
        f"Write a professional yet warm apology email for a delayed order. "
        f"Address the customer as {order['name'].split()[0]}. "
        f"Tone: genuinely apologetic and a little embarrassed about the delay, but remain composed and professional. "
        f"Reassure them their order is on its way and will be delivered shortly. "
        f"Keep it concise: subject line first, then 3-4 sentences. "
        f"Sign as 'AgentStudio Support Team'."
    )
    send_email(order["email"], subject, body, "delay_apology")
    log_email(order_id, "delay_apology")


def _on_delivered(order_id: str):
    if order_id in _timers:
        _timers.pop(order_id).cancel()
    order = get_order(order_id)
    if not order:
        return
    update_order(order_id, delivered_at=datetime.now(timezone.utc).isoformat(),
                 status="delivered")
    print(f"📦  [{order_id[:8]}] Order marked as delivered — waiting for review")


def _on_review(order_id: str, review_text: str):
    order = get_order(order_id)
    if not order:
        return
    update_order(order_id, review_text=review_text)

    no_comment = review_text.strip().lower() in ("no comment", "", "no comment.")
    sentiment = "NEUTRAL" if no_comment else _classify_sentiment(review_text)

    if sentiment == "NEGATIVE":
        delay_context = (
            "Note: this customer also experienced a delivery delay and already received an apology for it. "
            "Acknowledge this and show extra care. "
            if order["apology_sent"] else ""
        )
        subject, body = _llm_email(
            f"Write a professional and empathetic apology email in response to a negative customer review. "
            f"{delay_context}"
            f"Address the customer as {order['name'].split()[0]}. "
            f"Their review was: '{review_text}'. "
            f"Reference the specific issue they mentioned and show you understand what went wrong. "
            f"End with a clear invitation for them to reply directly to this email with more details so the team can assist them further. "
            f"Subject line first, then body. 4-5 sentences max. "
            f"Sign as 'AgentStudio Support Team'."
        )
        send_email(order["email"], subject, body, "review_apology")
        log_email(order_id, "review_apology")
    elif sentiment == "NEUTRAL":
        subject, body = _llm_email(
            f"Write a brief, friendly thank you email to a customer who just received their order. "
            f"Address the customer as {order['name'].split()[0]}. "
            f"Keep it simple and warm, just thank them for their order and wish them well. "
            f"Subject line first, then 2-3 sentences max. "
            f"Sign as 'AgentStudio Support Team'."
        )
        send_email(order["email"], subject, body, "thank_you")
        update_order(order_id, thankyou_sent=1)
        log_email(order_id, "thank_you")
    else:  # POSITIVE
        subject, body = _llm_email(
            f"Write a short, warm thank you email for a positive review. "
            f"Address the customer as {order['name'].split()[0]}. "
            f"Subject line first, then body. 3-4 sentences max. "
            f"Sign as 'AgentStudio Support Team'."
        )
        send_email(order["email"], subject, body, "thank_you")
        update_order(order_id, thankyou_sent=1)
        log_email(order_id, "thank_you")


# RabbitMQ message handler and consumer startup

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
