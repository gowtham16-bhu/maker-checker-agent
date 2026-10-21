"""A real support agent on Claude (Anthropic SDK tool runner), every tool call gated.

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python examples/claude_agent.py injection     # or: invoice, refund
"""

import sys

import anthropic
from anthropic import beta_tool

from support_tools import SAMPLE_EMAILS, SYSTEM_PROMPT, TOOLS, as_prompt, checker

email = SAMPLE_EMAILS[sys.argv[1] if len(sys.argv) > 1 else "injection"]
client = anthropic.Anthropic()

with checker.context(sender=email["from"]):
    runner = client.beta.messages.tool_runner(
        model="claude-opus-5-5",
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        tools=[beta_tool(tool) for tool in TOOLS],
        messages=[{"role": "user", "content": as_prompt(email)}],
    )
    final = None
    for message in runner:
        final = message

if final is None or final.stop_reason == "refusal":
    print("Claude declined this request.")
else:
    print("".join(block.text for block in final.content if block.type == "text"))
