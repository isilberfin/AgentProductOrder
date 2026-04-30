import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "orders.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id       TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                email          TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'pending',
                created_at     TEXT NOT NULL,
                delivered_at   TEXT,
                delayed_at     TEXT,
                apology_sent   INTEGER NOT NULL DEFAULT 0,
                thankyou_sent  INTEGER NOT NULL DEFAULT 0,
                review_text    TEXT,
                emails_sent    TEXT NOT NULL DEFAULT ''
            )
        """)


def create_order(order_id: str, name: str, email: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO orders (order_id, name, email, created_at) VALUES (?, ?, ?, ?)",
            (order_id, name, email, datetime.now(timezone.utc).isoformat()),
        )


def get_order(order_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
    return dict(row) if row else None


def update_order(order_id: str, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE orders SET {sets} WHERE order_id = ?",
            (*kwargs.values(), order_id),
        )


def log_email(order_id: str, email_type: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT emails_sent FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        existing = row["emails_sent"] if row else ""
        updated = (existing + f"|{email_type}").strip("|")
        conn.execute(
            "UPDATE orders SET emails_sent = ? WHERE order_id = ?",
            (updated, order_id),
        )


def get_all_orders() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


init_db()
