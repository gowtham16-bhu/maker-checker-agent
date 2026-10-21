"""Your rules, written as plain code.

The Gatekeeper runs these. No LLM is involved, so a clever email
can't talk its way past them.
"""

from __future__ import annotations

from .intents import Intent

COMPANY_DOMAIN = "acme.com"
REFUND_LIMIT = 100  # anything above this needs a human


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower()


def _is_internal(address: str) -> bool:
    return _domain(address) == COMPANY_DOMAIN


def check(intent: Intent, context: dict) -> str | None:
    """Return None if the action is allowed, or the reason it's denied.

    `context` holds trusted facts that did not come from the LLM,
    such as the real sender of the email.
    """
    sender = context.get("sender", "")

    if intent.tool == "send_email":
        to = intent.args.get("to", "")
        if to.lower() != sender.lower() and not _is_internal(to):
            return f"can only reply to the sender ({sender}) or {COMPANY_DOMAIN} staff, not {to}"
        return None

    if intent.tool == "issue_refund":
        amount = intent.args.get("amount")
        if not isinstance(amount, (int, float)) or amount <= 0:
            return "refund amount must be a positive number"
        if amount > REFUND_LIMIT:
            return f"refunds over ${REFUND_LIMIT} need a human to approve"
        return None

    if intent.tool == "export_customer_data":
        destination = intent.args.get("destination", "")
        if not _is_internal(destination):
            return f"customer data can only go to {COMPANY_DOMAIN} addresses, not {destination}"
        return None

    return f"unknown tool '{intent.tool}'"
