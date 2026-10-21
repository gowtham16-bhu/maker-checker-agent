"""A real support agent on the OpenAI Agents SDK, every tool call gated.

    pip install openai-agents
    export OPENAI_API_KEY=...
    python examples/openai_agent.py injection     # or: invoice, refund
"""

import sys

from agents import Agent, Runner, function_tool

from support_tools import SAMPLE_EMAILS, SYSTEM_PROMPT, TOOLS, as_prompt, checker

email = SAMPLE_EMAILS[sys.argv[1] if len(sys.argv) > 1 else "injection"]
agent = Agent(
    name="Acme support",
    instructions=SYSTEM_PROMPT,
    tools=[function_tool(tool) for tool in TOOLS],
)

with checker.context(sender=email["from"]):
    result = Runner.run_sync(agent, as_prompt(email))

print(result.final_output)
