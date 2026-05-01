import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import streamlit as st

from config import API_BASE_URL as API
from constants import DELAY_SECONDS, CHAT_WINDOW_SECONDS

PRODUCT = json.loads(
    (Path(__file__).parent.parent / "data" / "products.json").read_text()
)[0]

WELCOME_MSG = (
    "Hi there! 👋 I'm here to help you with the **SoundWave Pro Wireless Headphones** "
    "or any questions about your delivery. Feel free to ask!"
)

st.set_page_config(page_title="AgentStudio", page_icon="🎧", layout="wide")

# initialize session state defaults
for key, val in [("demo_started", False), ("demo_done", False),
                 ("order_id", None), ("created_at", None),
                 ("chat_history", [{"role": "assistant", "content": WELCOME_MSG}]),
                 ("show_review", False), ("waiting_for_response", False), ("buying", False),
                 ("pending_cancel", False), ("order_cancelled", False)]:
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
    st.session_state.waiting_for_response = False
    st.session_state.buying        = False
    st.session_state.pending_cancel = False
    st.session_state.order_cancelled = False


def product_card():
    img_path = Path(__file__).parent.parent / "data" / "headphone.png"
    with st.container(border=True):
        st.markdown(f"### 🎧 {PRODUCT['name']}")
        st.markdown(f"**${PRODUCT['price']}**")
        if img_path.exists():
            st.image(str(img_path), use_container_width=True)
        st.caption(PRODUCT["description"])
        st.divider()
        st.caption("• Color: Forest Green")
        for line in PRODUCT["specs"].split("|"):
            st.caption(f"• {line.strip()}")


# show end screen if order was cancelled
if st.session_state.order_cancelled:
    st.markdown("<br>" * 4, unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center'>🎉 Thank you for trying the demo!</h1>",
                unsafe_allow_html=True)
    st.stop()

# show thank you screen after review is submitted
if st.session_state.demo_done:
    st.markdown("<br>" * 4, unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center'>🎉 Thank you for trying the demo!</h1>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:gray'>📬 One last email is on its way, check your inbox for a follow-up based on your review.</p>",
                unsafe_allow_html=True)
    st.stop()

# review screen shown after delivery
if st.session_state.show_review:
    st.title("🎧 SoundWave Pro")
    st.subheader("✍️ Leave a Review (optional)")

    text = st.text_area("How was your experience?",
                        placeholder="Tell us what you think...")
    _, col1, col2, _ = st.columns([1, 1, 1, 1])
    with col1:
        if st.button("📝 Send Review", use_container_width=True):
            if text.strip():
                requests.post(
                    f"{API}/orders/{st.session_state.order_id}/review",
                    json={"review_text": text},
                )
                st.session_state.demo_done = True
                st.rerun()
            else:
                st.warning("Please enter a review")
    with col2:
        if st.button("Skip", use_container_width=True):
            requests.post(
                f"{API}/orders/{st.session_state.order_id}/review",
                json={"review_text": "No comment"},
            )
            st.session_state.demo_done = True
            st.rerun()
    st.stop()

# landing screen with start button
landing_slot = st.empty()
start_clicked = False

if not st.session_state.demo_started:
    with landing_slot.container():
        st.markdown("<br>" * 3, unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center'>🎧 AgentStudio</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:gray'>A demo project showcasing AI agents for automated order workflows, intelligent email handling, and RAG-based customer support</p>",
                    unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        col = st.columns([2, 1, 2])[1]
        with col:
            start_clicked = st.button("▶ Start Demo", use_container_width=True)

if start_clicked:
    st.session_state.demo_started = True
    landing_slot.empty()

if not st.session_state.demo_started:
    st.stop()

# main layout: product card on the left, order + chat on the right
prod_col, main_col = st.columns([1, 2], gap="large")

with prod_col:
    product_card()

with main_col:
    need_auto_refresh = False

    # order form for new users
    if st.session_state.order_id is None:
        st.subheader("Place Your Order")
        if not st.session_state.buying:
            with st.form("order_form"):
                col_fn, col_ln = st.columns(2)
                with col_fn:
                    first_name = st.text_input("First Name", placeholder="John")
                with col_ln:
                    last_name = st.text_input("Last Name", placeholder="Doe")
                email = st.text_input("Your email", placeholder="you@example.com")
                submitted = st.form_submit_button("🛒 Buy Now", use_container_width=True)
            if submitted:
                if first_name.strip() and last_name.strip() and email.strip():
                    name = f"{first_name.strip()} {last_name.strip()}"
                    st.session_state.buying = True
                    r = requests.post(f"{API}/orders", json={"name": name, "email": email})
                    if r.ok:
                        st.session_state.order_id   = r.json()["order_id"]
                        st.session_state.created_at = time.time()
                        st.session_state.buying = False
                        st.rerun()
                    else:
                        st.session_state.buying = False
                        st.error("Could not place order.")
                else:
                    st.warning("Please fill in your first name, last name, and email.")
        else:
            st.info("⏳ Processing your order...")

    # order tracking screen
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

        # render status-specific UI
        if status == "pending":
            st.subheader("⏳ Your order is on its way!")
            remaining = max(0, DELAY_SECONDS - elapsed)
            st.progress(1 - remaining / DELAY_SECONDS,
                        text=f"Estimated arrival in {int(remaining)}s")
            st.info(
                "**Demo tip:** Estimated arrival time is **30 seconds**. "
                "To trigger the demo flow for receiving your product, click the button below!\n\n"
                "⚠️ If you don't click the button: after **30 seconds** you'll receive an apology email for the delay "
                "from **agentmailyourorder@11128390.brevosend.com** (please check your spam folder!), "
                "and after **5 minutes** you'll be automatically taken to the review page.\n\n"
                "💬 Feel free to ask about your order or product information in the support chat below, the chat will remain available until you reach the review page, which will be 5 minutes after the delay notification!"
            )
            if st.button("📦 I received the product"):
                requests.post(f"{API}/orders/{order['order_id']}/deliver")
                st.session_state.show_review = True
                st.rerun()

        elif status == "delayed":
            delayed_at = datetime.fromisoformat(order["delayed_at"].replace("Z", ""))
            secs_since = (datetime.now(timezone.utc) -
                          delayed_at.replace(tzinfo=timezone.utc)).total_seconds()
            remaining_chat = max(0, CHAT_WINDOW_SECONDS - secs_since)
            st.subheader("⚠️ Status: Delayed")
            st.info(
                "We're sorry for the delay! An apology email has been sent to you from **agentmailyourorder@11128390.brevosend.com**, "
                "please check your **spam folder** if you don't see it.\n\n"
                "⏱️ You will be automatically directed to the review page in **5 minutes**. "
                "To trigger it now, click the button below, or feel free to use the support chat meanwhile!"
            )
            if st.button("📦 I received the product"):
                requests.post(f"{API}/orders/{order['order_id']}/deliver")
                st.session_state.show_review = True
                st.rerun()

        elif status == "delivered":
            st.session_state.show_review = True
            st.rerun()


        # schedule auto-refresh after chat renders
        if status in ("pending", "delayed") and not st.session_state.waiting_for_response:
            need_auto_refresh = True

    # support chat, visible until the review screen appears
    if not st.session_state.show_review and not st.session_state.buying:
        st.divider()
        st.subheader("💬 Support")
        chat_box = st.container(height=340)
        with chat_box:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"].replace("$", r"\$"))

        # Chat input always visible
        user_input = st.chat_input("Ask about your order or product...")
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            lowered = user_input.strip().lower()
            # handle pending cancellation confirmation
            if st.session_state.pending_cancel:
                if any(w in lowered for w in ["yes", "yeah", "yep", "sure", "ok", "okay", "do it", "confirm"]):
                    r = requests.post(f"{API}/orders/{st.session_state.order_id}/cancel", timeout=5)
                    if r.ok and r.json().get("ok"):
                        st.session_state.order_cancelled = True
                    else:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": "Your order can no longer be cancelled as the 30-second window has passed."
                        })
                    st.session_state.pending_cancel = False
                elif any(w in lowered for w in ["no", "nope", "don't", "dont", "keep"]):
                    st.session_state.pending_cancel = False
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "No problem! Your order is still active."
                    })
                else:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "Please reply **yes** to confirm cancellation or **no** to keep your order."
                    })
                st.rerun()

            else:
                st.session_state.waiting_for_response = True
                st.rerun()

        # Get AI response on next render (if waiting)
        if st.session_state.waiting_for_response:
            try:
                # Use pre-order chat if no order yet, otherwise use order-specific chat
                if st.session_state.order_id:
                    url = f"{API}/orders/{st.session_state.order_id}/chat"
                else:
                    url = f"{API}/chat"
                
                history = st.session_state.chat_history
                last_bot = next(
                    (m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"),
                    ""
                )
                r = requests.post(
                    url,
                    json={
                        "message": history[-1]["content"],
                        "last_bot_message": last_bot,
                        "history": history[:-1],
                    },
                    timeout=10,
                )
                reply = (r.json().get("response", "Sorry, I couldn't process that.")
                         if r.ok else "Error contacting support.")
                # if LLM detected cancellation intent, handle it here
                if reply.strip() == "__CANCEL__":
                    can_cancel = (st.session_state.order_id and
                                  time.time() - (st.session_state.created_at or 0) < DELAY_SECONDS)
                    if can_cancel:
                        st.session_state.pending_cancel = True
                        reply = "Are you sure you want to cancel your order? Reply **yes** to confirm or **no** to keep it."
                    else:
                        reply = "Your order can no longer be cancelled as the 30-second window has passed."
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": reply}
                )
            except Exception:
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": "Error connecting to support."}
                )
            finally:
                st.session_state.waiting_for_response = False
                st.rerun()

    if need_auto_refresh:
        time.sleep(1)
        st.rerun()

