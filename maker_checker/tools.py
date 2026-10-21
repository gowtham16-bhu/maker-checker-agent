"""Simulated business tools. They only write files inside a sandbox folder,
so the demo never sends a real email or moves real money."""

from __future__ import annotations

import json
from pathlib import Path

CUSTOMERS = [
    {"id": 1, "name": "Alice Kumar", "email": "alice@gmail.com", "card_last4": "4242"},
    {"id": 2, "name": "Bob Lee", "email": "bob@yahoo.com", "card_last4": "1881"},
    {"id": 3, "name": "Chen Wu", "email": "chen@outlook.com", "card_last4": "9090"},
]


def make_tools(sandbox: Path) -> dict:
    sandbox = Path(sandbox)
    (sandbox / "outbox").mkdir(parents=True, exist_ok=True)

    def send_email(to: str, subject: str, body: str) -> str:
        count = len(list((sandbox / "outbox").iterdir()))
        path = sandbox / "outbox" / f"{count + 1:03d}.txt"
        path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n")
        return f"email sent to {to}"

    def issue_refund(order_id: str, amount: float) -> str:
        with (sandbox / "refunds.csv").open("a") as f:
            f.write(f"{order_id},{amount}\n")
        return f"refunded ${amount} on order {order_id}"

    def export_customer_data(destination: str) -> str:
        path = sandbox / "outbox" / "customer_export.json"
        path.write_text(json.dumps({"to": destination, "customers": CUSTOMERS}, indent=2))
        return f"exported {len(CUSTOMERS)} customer records to {destination}"

    return {
        "send_email": send_email,
        "issue_refund": issue_refund,
        "export_customer_data": export_customer_data,
    }
