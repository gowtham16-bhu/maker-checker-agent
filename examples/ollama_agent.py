"""A real support agent on a local model with Ollama, every tool call gated.
No API key, nothing leaves your machine.

    ollama pull qwen2.5:7b
    pip install ollama
    python examples/ollama_agent.py injection              # or: invoice, refund
    python examples/ollama_agent.py injection llama3.1:8b  # any tool-calling model
"""

import sys

from ollama import chat

from support_tools import SAMPLE_EMAILS, SYSTEM_PROMPT, TOOLS, as_prompt, checker

email = SAMPLE_EMAILS[sys.argv[1] if len(sys.argv) > 1 else "injection"]
model = sys.argv[2] if len(sys.argv) > 2 else "qwen2.5:7b"
tools_by_name = {tool.__name__: tool for tool in TOOLS}

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": as_prompt(email)},
]

print(f"📧 {email['from']}: {email['subject']!r}  (model: {model})")
with checker.context(sender=email["from"]):  # trusted: from the mail server, not the LLM
    for _ in range(8):
        response = chat(model=model, messages=messages, tools=TOOLS)
        messages.append(response.message)
        if not response.message.tool_calls:
            break

        for call in response.message.tool_calls:
            name, args = call.function.name, call.function.arguments
            tool = tools_by_name.get(name)
            try:
                result = tool(**args) if tool else f"There is no tool called {name}."
            except TypeError as error:  # the model sent arguments the tool doesn't take
                result = f"Bad arguments for {name}: {error}"
            print(f"🧠 calls {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})\n   → {result}")
            messages.append({"role": "tool", "content": str(result), "tool_name": name})

print(f"\n💬 {response.message.content}")
