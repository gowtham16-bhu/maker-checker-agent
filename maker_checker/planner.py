"""Role 1: the Planner (the "maker").

The only role that uses an LLM. It reads the messy, untrusted email and
proposes actions. It has no way to run them: its tool calls come back as
data, and the pipeline hands them to the Gatekeeper.
"""

from __future__ import annotations

import re

from .intents import Email, Intent

SYSTEM_PROMPT = """You are the planning step of Acme's customer-support agent.
Read the email and propose the tool calls needed to handle it.
Your tool calls are proposals: a separate policy check decides what actually runs."""

TOOLS = [
    {
        "name": "send_email",
        "description": "Send an email.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund an order.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["order_id", "amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "export_customer_data",
        "description": "Export the customer database to an email address.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"destination": {"type": "string"}},
            "required": ["destination"],
            "additionalProperties": False,
        },
    },
]


class ClaudePlanner:
    """Uses Claude to propose actions. Needs `pip install anthropic` and an
    ANTHROPIC_API_KEY (or an `ant auth login` profile)."""

    def __init__(self, model: str = "claude-opus-5-5"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def plan(self, email: Email) -> list[Intent]:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=[
                {
                    "role": "user",
                    "content": f"From: {email.sender}\nSubject: {email.subject}\n\n{email.body}",
                }
            ],
        )
        if response.stop_reason == "refusal":
            return []
        return [
            Intent(tool=block.name, args=dict(block.input), reason="proposed by Claude")
            for block in response.content
            if block.type == "tool_use"
        ]


class ScriptedPlanner:
    """Stands in for an LLM so the demo runs offline with no API key.

    It behaves like a model that has fallen for a prompt injection: it does
    whatever the email text asks. That's the worst case the other three
    roles are there to contain.
    """

    def plan(self, email: Email) -> list[Intent]:
        text = email.body
        intents = []

        if re.search(r"\binvoice\b", text, re.I):
            intents.append(
                Intent(
                    "send_email",
                    {"to": email.sender, "subject": f"Re: {email.subject}", "body": "Here is your invoice."},
                    "the customer asked for their invoice",
                )
            )

        refund = re.search(r"refund (?:of )?\$(\d+(?:\.\d+)?)", text, re.I)
        if refund:
            order = re.search(r"order #?(\d+)", text, re.I)
            amount = float(refund.group(1))
            intents.append(
                Intent(
                    "issue_refund",
                    {
                        "order_id": order.group(1) if order else "unknown",
                        "amount": int(amount) if amount.is_integer() else amount,
                    },
                    "the customer asked for a refund",
                )
            )

        export = re.search(r"send (?:the )?(?:full )?customer (?:database|data|list) to ([\w.+-]+@[\w-]+(?:\.[\w-]+)+)", text, re.I)
        if export:
            intents.append(
                Intent("export_customer_data", {"destination": export.group(1)}, "the email told it to")
            )

        return intents
