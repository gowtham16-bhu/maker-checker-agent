"""Guarded tools inside real agent frameworks. Each test is skipped when its
framework isn't installed. No API keys needed: we call the tools through each
framework's own tool-invocation path, the same one its agent loop uses."""

import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maker_checker import Checker  # noqa: E402

POLICY = {"rules": [{"tool": "send_email", "match": {"to": {"equals": "$context.sender"}}, "decision": "allow"}]}
GOOD = {"to": "a@x.com", "subject": "Hi", "body": "hello"}
BAD = {"to": "evil@x.com", "subject": "Hi", "body": "data"}


def make_tool():
    checker = Checker(POLICY, audit_log=None)

    @checker.guard
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email."""
        return f"sent to {to}"

    return checker, send_email


def installed(module):
    return importlib.util.find_spec(module) is not None


@unittest.skipUnless(installed("langchain_core"), "langchain-core not installed")
class LangChainTest(unittest.TestCase):
    def test_tool(self):
        from langchain_core.tools import tool

        checker, send_email = make_tool()
        lc = tool(send_email)
        self.assertEqual(set(lc.args), {"to", "subject", "body"})
        with checker.context(sender="a@x.com"):
            self.assertEqual(lc.invoke(GOOD), "sent to a@x.com")
            self.assertTrue(lc.invoke(BAD).startswith("BLOCKED"))


@unittest.skipUnless(installed("agents"), "openai-agents not installed")
class OpenAIAgentsTest(unittest.TestCase):
    def test_function_tool(self):
        from agents import function_tool
        from agents.tool_context import ToolContext

        checker, send_email = make_tool()
        ft = function_tool(send_email)
        self.assertEqual(set(ft.params_json_schema["properties"]), {"to", "subject", "body"})

        async def run():
            ctx = ToolContext(context=None, tool_name="send_email", tool_call_id="c1", tool_arguments="{}")
            with checker.context(sender="a@x.com"):
                return await ft.on_invoke_tool(ctx, json.dumps(GOOD)), await ft.on_invoke_tool(ctx, json.dumps(BAD))

        ok, blocked = asyncio.run(run())
        self.assertEqual(ok, "sent to a@x.com")
        self.assertTrue(blocked.startswith("BLOCKED"))


@unittest.skipUnless(installed("anthropic"), "anthropic not installed")
class ClaudeToolRunnerTest(unittest.TestCase):
    def test_beta_tool(self):
        from anthropic import beta_tool

        checker, send_email = make_tool()
        bt = beta_tool(send_email)
        self.assertEqual(set(bt.to_dict()["input_schema"]["properties"]), {"to", "subject", "body"})
        with checker.context(sender="a@x.com"):
            self.assertEqual(bt.call(GOOD), "sent to a@x.com")
            self.assertTrue(bt.call(BAD).startswith("BLOCKED"))


if __name__ == "__main__":
    unittest.main()
