import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from config import OPENAI_API_KEY
from worker.rag import retrieve, retrieve_order

llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=300, temperature=0)


class ChatState(TypedDict):
    order_id: str
    message: str
    elapsed_seconds: float
    classification: str
    response: str


# ── nodes ──────────────────────────────────────────────────────────────────────

def classify(state: ChatState) -> ChatState:
    """Route the customer message to product, order, or unrelated."""
    response = llm.invoke([HumanMessage(content=(
        "Classify this customer message into exactly one category:\n"
        "- product   (features, specs, warranty, return policy, compatibility)\n"
        "- order     (status, shipping, delivery, where is my order, delay)\n"
        "- unrelated (anything else)\n\n"
        f"Message: \"{state['message']}\"\n\n"
        "Reply with one word only: product, order, or unrelated."
    ))])
    raw = response.content.strip().lower()
    if "product" in raw:
        cls = "product"
    elif "order" in raw:
        cls = "order"
    else:
        cls = "unrelated"
    return {**state, "classification": cls}


def answer_product(state: ChatState) -> ChatState:
    """Answer product questions using RAG over the products Pinecone namespace."""
    docs = retrieve(state["message"])
    if docs:
        context = "\n\n".join(docs)
        response = llm.invoke([HumanMessage(content=(
            "You are a helpful product support agent. "
            "Answer the customer question using only the product information below. "
            "If the answer is not in the context, say you don't have that information.\n\n"
            f"Product info:\n{context}\n\n"
            f"Customer question: {state['message']}"
        ))])
        answer = response.content.strip()
    else:
        answer = "I couldn't find specific product information for your question. Please contact our support team."
    return {**state, "response": answer}


def answer_order(state: ChatState) -> ChatState:
    """Answer order/delivery questions using RAG over order-procedures + live elapsed time."""
    elapsed = state["elapsed_seconds"]
    docs = retrieve_order(state["message"])
    context = "\n\n".join(docs) if docs else ""

    if elapsed < 60:
        remaining = max(1, int(60 - elapsed))
        delivery_status = (
            f"The order is currently being processed and should arrive in about {remaining} second(s)."
        )
    else:
        secs_delayed = int(elapsed - 60)
        delivery_status = (
            f"The order is delayed (delayed {secs_delayed}s ago). "
            "A delay apology email has been sent. The order will arrive within 5 minutes of the delay notification."
        )

    response = llm.invoke([HumanMessage(content=(
        "You are a helpful order support agent for AgentMail. "
        "Answer the customer's question using the order procedures below and the current delivery status. "
        "Be concise, friendly, and accurate.\n\n"
        f"Order procedures:\n{context}\n\n"
        f"Current delivery status: {delivery_status}\n\n"
        f"Customer question: {state['message']}"
    ))])
    return {**state, "response": response.content.strip()}


def answer_unrelated(state: ChatState) -> ChatState:
    """Handle off-topic messages with a polite redirect to order or product questions."""
    response = llm.invoke([HumanMessage(content=(
        "You are a friendly e-commerce customer support agent. "
        "Answer the following question briefly. "
        "If it is completely off-topic, politely redirect to order or product questions.\n\n"
        f"Question: {state['message']}"
    ))])
    return {**state, "response": response.content.strip()}


# ── routing ────────────────────────────────────────────────────────────────────

def route(state: ChatState) -> str:
    """Return the classification label used by the conditional edge."""
    return state["classification"]


# ── build graph ────────────────────────────────────────────────────────────────

def build_chat_graph():
    g = StateGraph(ChatState)
    g.add_node("classify",         classify)
    g.add_node("answer_product",   answer_product)
    g.add_node("answer_order",     answer_order)
    g.add_node("answer_unrelated", answer_unrelated)

    g.set_entry_point("classify")
    g.add_conditional_edges("classify", route, {
        "product":   "answer_product",
        "order":     "answer_order",
        "unrelated": "answer_unrelated",
    })
    g.add_edge("answer_product",   END)
    g.add_edge("answer_order",     END)
    g.add_edge("answer_unrelated", END)
    return g.compile()


_chat_graph = build_chat_graph()


def chat(order_id: str, message: str, elapsed_seconds: float) -> str:
    """Entry point called by the API. Returns the agent's reply string."""
    result = _chat_graph.invoke({
        "order_id":        order_id,
        "message":         message,
        "elapsed_seconds": elapsed_seconds,
        "classification":  "",
        "response":        "",
    })
    return result["response"]
