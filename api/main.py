import json
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pika
from fastapi import FastAPI
from pydantic import BaseModel

from config import RABBITMQ_URL
from constants import QUEUE
from state.store import create_order, get_order, update_order, get_all_orders
from worker.chat_graph import chat

app = FastAPI()


def publish(event: str, order_id: str, **extra):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=json.dumps({"event": event, "order_id": order_id, **extra}),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    connection.close()


class BuyRequest(BaseModel):
    name: str
    email: str


class ReviewRequest(BaseModel):
    review_text: str


@app.post("/orders")
def buy(req: BuyRequest):
    order_id = str(uuid.uuid4())
    create_order(order_id, req.name, req.email)
    publish("order_created", order_id, name=req.name, email=req.email)
    return {"order_id": order_id}


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str):
    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return {"error": "cannot cancel"}
    update_order(order_id, status="cancelled")
    return {"ok": True}


@app.post("/orders/{order_id}/trigger-delay")
def trigger_delay(order_id: str):
    import threading
    from worker.consumer import _on_timeout
    threading.Thread(target=_on_timeout, args=[order_id], daemon=True).start()
    return {"ok": True}


@app.post("/orders/{order_id}/deliver")
def deliver(order_id: str):
    order = get_order(order_id)
    if not order:
        return {"error": "not found"}
    publish("order_delivered", order_id)
    return {"ok": True}


@app.post("/orders/{order_id}/review")
def review(order_id: str, req: ReviewRequest):
    update_order(order_id, review_text=req.review_text)
    publish("review_submitted", order_id, review_text=req.review_text)
    return {"ok": True}


@app.get("/orders/{order_id}")
def get_one(order_id: str):
    return get_order(order_id) or {"error": "not found"}


@app.get("/orders")
def list_orders():
    return get_all_orders()


class ChatRequest(BaseModel):
    message: str
    last_bot_message: str = ""
    history: list[dict] = []


@app.post("/chat")
def general_chat(req: ChatRequest):
    """Chat before ordering - for product questions"""
    response = chat(None, req.message, 0, req.last_bot_message, req.history)
    return {"response": response}


@app.post("/orders/{order_id}/chat")
def chat_endpoint(order_id: str, req: ChatRequest):
    order = get_order(order_id)
    if not order:
        return {"error": "not found"}
    created_at = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)
               if created_at.tzinfo is None
               else (datetime.now(timezone.utc) - created_at)).total_seconds()
    response = chat(order_id, req.message, elapsed, req.last_bot_message, req.history)
    return {"response": response}
