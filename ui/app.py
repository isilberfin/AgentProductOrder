import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import streamlit as st

API  = "http://localhost:8000"
DELAY_SECONDS       = 60
CHAT_WINDOW_SECONDS = 300

PRODUCT = json.loads(
    (Path(__file__).parent.parent / "data" / "products.json").read_text()
)[0]

WELCOME_MSG = (
    "Hi there! 👋 I'm here to help you with the **SoundWave Pro Wireless Headphones** "
    "or any questions about your delivery. Feel free to ask!"
)

st.set_page_config(page_title="AgentMail", page_icon="🎧", layout="wide")

# ── session init ───────────────────────────────────────────────────────────────
for key, val in [("demo_started", False), ("demo_done", False),
                 ("order_id", None), ("created_at", None),
                 ("chat_history", [{"role": "assistant", "content": WELCOME_MSG}]),
                 ("show_review", False)]:
    if key not in st.session_state:
        st.session_state[key] = val


def fetch_order():
    if not st.session_state.order_id:
        return None
    try:
        r = requests.get(f"{API}/orders/{st.session_state.order_id}", timeout=2)
        return r.json() if r.ok else None
    except Exception:
        return None


def reset():
    st.session_state.demo_started  = False
    st.session_state.demo_done     = False
    st.session_state.order_id      = None
    st.session_state.created_at    = None
    st.session_state.chat_history  = [{"role": "assistant", "content": WELCOME_MSG}]
    st.session_state.show_review   = False


def product_card():
    colors    = PRODUCT["colors"]
    color_dots = {"Midnight Black": "⚫", "Arctic White": "⚪",
                  "Navy Blue": "🔵", "Rose Gold": "🟤", "Forest Green": "🟢"}
    with st.container(border=True):
        st.markdown(f"### 🎧 {PRODUCT['name']}")
        st.markdown(f"**${PRODUCT['price']}**")
        st.caption(PRODUCT["description"])
        st.divider()
        st.markdown("**Available Colors**")
        cols = st.columns(len(colors["available"]))
        for i, c in enumerate(colors["available"]):
            with cols[i]:
                st.markdown(f"{color_dots.get(c, '🔘')} {c}")
        if colors.get("limited_edition"):
            st.caption(f"✨ Limited edition: {', '.join(colors['limited_edition'])}")
        st.divider()
        for line in PRODUCT["specs"].split("|"):
            st.caption(f"• {line.strip()}")


# ── THANK YOU screen ───────────────────────────────────────────────────────────
if st.session_state.demo_done:
    st.markdown("<br>" * 4, unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center'>🎉 Thank you for trying the demo!</h1>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:gray'>AgentMail — AI-powered order management</p>",
                unsafe_allow_html=True)
    st.stop()

# ── REVIEW screen ──────────────────────────────────────────────────────────────
if st.session_state.show_review:
    st.title("🎧 SoundWave Pro")
    st.subheader("✍️ Leave a Review (optional)")

    text = st.text_area("How was your experience?",
                        placeholder="Tell us what you think...")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 Send Review", disabled=not text.strip()):
            requests.post(
                f"{API}/orders/{st.session_state.order_id}/review",
                json={"review_text": text},
            )
            st.session_state.demo_done = True
            st.rerun()
    with col2:
        if st.button("Skip"):
            st.session_state.demo_done = True
            st.rerun()
    st.stop()

# ── LANDING screen ─────────────────────────────────────────────────────────────
if not st.session_state.demo_started:
    st.markdown("<br>" * 3, unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center'>🎧 AgentMail</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:gray'>AI-powered order management & customer support</p>",
                unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    col = st.columns([2, 1, 2])[1]
    with col:
        if st.button("▶ Start Demo", use_container_width=True, type="primary"):
            st.session_state.demo_started = True
            st.rerun()
    st.stop()

# ── main layout: product | order+chat ─────────────────────────────────────────
prod_col, main_col = st.columns([1, 2], gap="large")

with prod_col:
    product_card()

with main_col:
    # ── BUY screen ─────────────────────────────────────────────────────────────
    if st.session_state.order_id is None:
        st.subheader("Place Your Order")
        email = st.text_input("Your email", placeholder="you@example.com")
        if st.button("🛒 Buy Now", disabled=not email.strip()):
            r = requests.post(f"{API}/orders", json={"email": email})
            if r.ok:
                st.session_state.order_id   = r.json()["order_id"]
                st.session_state.created_at = time.time()
                st.rerun()
            else:
                st.error("Could not place order.")

    # ── ORDER + CHAT screen ─────────────────────────────────────────────────────
    else:
        order = fetch_order()
        if not order or "error" in order:
            st.error("Order not found.")
            st.stop()

        elapsed = time.time() - st.session_state.created_at
        status  = order["status"]

        # 5-min auto-deliver after delay
        if status == "delayed" and order.get("delayed_at"):
            delayed_at = datetime.fromisoformat(order["delayed_at"].replace("Z", ""))
            secs_since = (datetime.now(timezone.utc) -
                          delayed_at.replace(tzinfo=timezone.utc)).total_seconds()
            if secs_since >= CHAT_WINDOW_SECONDS:
                requests.post(f"{API}/orders/{order['order_id']}/deliver")
                st.session_state.show_review = True
                st.rerun()

        order_col, chat_col = st.columns([1, 1], gap="medium")

        # ── order status ────────────────────────────────────────────────────────
        with order_col:
            if status == "pending":
                st.subheader("⏳ Processing")
                remaining = max(0, DELAY_SECONDS - elapsed)
                st.progress(1 - remaining / DELAY_SECONDS,
                            text=f"Delivery in ~{int(remaining)}s")
                if st.button("📦 I received the product", type="secondary"):
                    requests.post(f"{API}/orders/{order['order_id']}/deliver")
                    st.session_state.show_review = True
                    st.rerun()

            elif status == "delayed":
                delayed_at = datetime.fromisoformat(order["delayed_at"].replace("Z", ""))
                secs_since = (datetime.now(timezone.utc) -
                              delayed_at.replace(tzinfo=timezone.utc)).total_seconds()
                remaining_chat = max(0, CHAT_WINDOW_SECONDS - secs_since)
                st.subheader("⚠️ Delayed")
                st.info("Apology email sent.")
                st.progress(1 - remaining_chat / CHAT_WINDOW_SECONDS,
                            text=f"Auto-delivering in {int(remaining_chat)}s")
                if st.button("📦 I received the product", type="secondary"):
                    requests.post(f"{API}/orders/{order['order_id']}/deliver")
                    st.session_state.show_review = True
                    st.rerun()

            elif status == "delivered":
                st.session_state.show_review = True
                st.rerun()

            # email log
            emails = order.get("emails_sent", "")
            if emails:
                st.divider()
                st.caption("📬 Emails sent")
                for e in emails.split("|"):
                    if e:
                        st.caption(f"• {e.replace('_', ' ').title()}")

        # ── chat (only while waiting for delivery) ──────────────────────────────
        with chat_col:
            st.subheader("💬 Support")
            chat_box = st.container(height=340)
            with chat_box:
                for msg in st.session_state.chat_history:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])

            user_input = st.chat_input("Ask about your order or product...")
            if user_input:
                st.session_state.chat_history.append(
                    {"role": "user", "content": user_input}
                )
                r = requests.post(
                    f"{API}/orders/{order['order_id']}/chat",
                    json={"message": user_input},
                )
                reply = (r.json().get("response", "Sorry, I couldn't process that.")
                         if r.ok else "Error contacting support.")
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": reply}
                )
                st.rerun()

        # auto-refresh for progress bar (outside columns so chat renders first)
        if status in ("pending", "delayed"):
            time.sleep(2)
            st.rerun()

        with st.sidebar:
            if st.button("🔄 New Order"):
                reset()
                st.rerun()
