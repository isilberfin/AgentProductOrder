import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from config import OPENAI_API_KEY
from constants import KINDNESS_MSG
from worker.r2 import fetch_text
from worker.rag import retrieve, retrieve_order

try:
    _BAD_WORDS: set[str] = {
        w.strip().lower()
        for w in fetch_text("bad-words.txt").splitlines()
        if w.strip()
    }
except Exception:
    _BAD_WORDS = set()


def _is_inappropriate(text: str) -> bool:
    lowered = text.lower()
    matched = [w for w in _BAD_WORDS if w in lowered]
    if not matched:
        return False
    # LLM confirms whether the message is actually inappropriate in context
    sample = ", ".join(matched[:20])
    result = llm.invoke([HumanMessage(content=(
        f"The following words were detected in a customer support message: {sample}\n"
        f"Message: \"{text}\"\n\n"
        "Is this message inappropriate, offensive, or harmful in context? "
        "Reply with YES or NO only."
    ))])
    return "YES" in _to_str(result.content).strip().upper()


def _build_messages(system_prompt: str, history: list, current_message: str) -> list:
    msgs = [SystemMessage(content=system_prompt)]
    for m in history:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            msgs.append(AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=current_message))
    return msgs


def _to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item["text"] if isinstance(item, dict) and "text" in item else str(item)
            for item in content
        )
    return str(content)


def _extract_question(chunk: str) -> str:
    for line in chunk.split("\n"):
        if line.startswith("Q:"):
            return line[2:].strip()
    return chunk[:100]

llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=300, temperature=0.3)


class ChatState(TypedDict):
    order_id: str
    message: str
    elapsed_seconds: float
    classification: str
    response: str
    last_bot_message: str
    history: list


# graph nodes

def classify(state: ChatState) -> ChatState:
    response = llm.invoke([HumanMessage(content=(
        "Classify this customer message into exactly one category:\n"
        "- product   (features, specs, warranty, return policy, compatibility)\n"
        "- order     (status, shipping, delivery, where is my order, delay)\n"
        "- unrelated (anything else)\n\n"
        f"Message: \"{state['message']}\"\n\n"
        "Reply with one word only: product, order, or unrelated."
    ))])
    raw = _to_str(response.content).strip().lower()
    if "product" in raw:
        cls = "product"
    elif "order" in raw:
        cls = "order"
    else:
        cls = "unrelated"
    return {**state, "classification": cls}


def answer_product(state: ChatState) -> ChatState:
    docs = retrieve(state["message"])
    if docs:
        context = "\n\n".join(docs)
        system_prompt = (
            "You are a helpful product support agent. "
            "Answer the customer question using the product information below. "
            "If the exact answer is not stated, reason from what you know about the product — "
            "infer from the product's connectivity specs and purpose to give a clear, helpful answer. "
            "Never just say you don't have information if you can logically derive the answer.\n\n"
            f"Product info:\n{context}"
        )
        response = llm.invoke(_build_messages(system_prompt, state.get("history", []), state["message"]))
        answer = _to_str(response.content).strip()
    else:
        answer = "I couldn't find specific product information for your question. Please contact our support team."
    return {**state, "response": answer}


def answer_order(state: ChatState) -> ChatState:
    elapsed = state["elapsed_seconds"]
    docs = retrieve_order(state["message"], n=3)
    context = "\n\n".join(docs) if docs else ""

    if not state.get("order_id"):
        delivery_status = "The customer has not placed an order yet."
    elif elapsed < 30:
        remaining = max(1, int(30 - elapsed))
        delivery_status = (
            f"The order is currently being processed and should arrive in about {remaining} second(s)."
        )
    else:
        secs_delayed = int(elapsed - 30)
        delivery_status = (
            f"The order is delayed (delayed {secs_delayed}s ago). "
            "A delay apology email has been sent. The order will arrive within 5 minutes of the delay notification."
        )

    questions = [_extract_question(doc) for doc in docs]
    faq_titles = "\n".join(f"- {q}" for q in questions)

    system_prompt = (
        "You are a helpful order support agent for AgentStudio. "
        "Answer the customer's question using the order procedures below and the current delivery status. "
        "Be concise, friendly, and accurate.\n"
        "You have these related FAQ topics available — if the customer's question is related to any of them, answer it directly even if phrased differently:\n"
        f"{faq_titles}\n\n"
        "Reply with exactly the word SUGGEST (and nothing else) if: the question is too vague to answer specifically, OR you would otherwise give a generic non-answer like 'feel free to ask' or 'I'm here to help'. "
        "If you can give a real, specific answer — do so. If not — SUGGEST.\n"
        "If the customer expresses any desire to cancel, stop, or not want their order anymore (e.g. 'I don't want it', 'I changed my mind', 'stop my order', 'never mind'), reply with exactly __CANCEL__ and nothing else.\n"
        "If the delivery status says the customer has not placed an order yet, append a short note at the end of your answer reminding them that they have not placed an order yet.\n\n"
        f"Order procedures:\n{context}\n\n"
        f"Current delivery status: {delivery_status}"
    )
    response = llm.invoke(_build_messages(system_prompt, state.get("history", []), state["message"]))

    answer = _to_str(response.content).strip()
    if answer.upper() == "SUGGEST":
        already_suggested = "Did you mean one of these?" in state.get("last_bot_message", "")
        if already_suggested:
            answer = (
                "I'm sorry, I still couldn't fully understand your question. "
                "Could you try rephrasing it? I'll do my best to help you."
            )
        else:
            numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
            answer = f"I'm not sure I understood your question. Did you mean one of these?\n\n{numbered}"

    return {**state, "response": answer}


def answer_unrelated(state: ChatState) -> ChatState:
    system_prompt = (
        "You are a friendly e-commerce customer support agent. "
        "Answer the following question briefly. "
        "If it is completely off-topic, politely redirect to order or product questions."
    )
    response = llm.invoke(_build_messages(system_prompt, state.get("history", []), state["message"]))
    return {**state, "response": _to_str(response.content).strip()}


# conditional routing based on classification

def route(state: ChatState) -> str:
    return state["classification"]


# build and compile the langgraph state machine

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


def chat(order_id: str, message: str, elapsed_seconds: float,
         last_bot_message: str = "", history: list = []) -> str:
    """Entry point called by the API. Returns the agent's reply string."""
    if _is_inappropriate(message):
        return KINDNESS_MSG

    payload = {
        "order_id":        order_id,
        "message":         message,
        "elapsed_seconds": elapsed_seconds,
        "classification":  "",
        "response":        "",
        "last_bot_message": last_bot_message,
        "history":         history,
    }
    for _ in range(3):
        result = _chat_graph.invoke(payload)
        response = result["response"]
        if not _is_inappropriate(response):
            return response
    return "I didn't quite understand what you mean — could you rephrase that? I'll do my best to help!"
