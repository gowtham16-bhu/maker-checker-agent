"""A real support agent on the OpenAI Agents SDK, every tool call gated.

    pip install openai-agents

    # with OpenAI
    export OPENAI_API_KEY=...
    python examples/openai_agent.py injection          # or: invoice, refund

    # or fully local with Ollama (no API key)
    OLLAMA_MODEL=qwen2.5:7b python examples/openai_agent.py injection
"""

import os
import sys

from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
from openai import AsyncOpenAI

from support_tools import SAMPLE_EMAILS, SYSTEM_PROMPT, TOOLS, as_prompt, checker

model = None
if os.environ.get("OLLAMA_MODEL"):
    set_tracing_disabled(True)  # tracing uploads to OpenAI; nothing to upload to here
    model = OpenAIChatCompletionsModel(
        model=os.environ["OLLAMA_MODEL"],
        openai_client=AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
    )

email = SAMPLE_EMAILS[sys.argv[1] if len(sys.argv) > 1 else "injection"]
agent = Agent(
    name="Acme support",
    instructions=SYSTEM_PROMPT,
    tools=[function_tool(tool) for tool in TOOLS],
    **({"model": model} if model else {}),
)

with checker.context(sender=email["from"]):  # trusted: from the mail server, not the LLM
    result = Runner.run_sync(agent, as_prompt(email))

print(result.final_output)
