import asyncio
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maker_checker import Blocked, Checker, Doer, Gatekeeper, Intent, NotApproved, Policy  # noqa: E402

POLICY = {
    "default": "deny",
    "rules": [
        {"tool": "send_email", "match": {"to": {"equals": "$context.sender"}}, "decision": "allow"},
        {"tool": "refund", "match": {"amount": {"max": 100}}, "decision": "allow"},
        {"tool": "refund", "decision": "ask", "reason": "big refund"},
    ],
}


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, **kwargs):
        checker = Checker(POLICY, audit_log=self.log, **kwargs)

        @checker.guard
        def send_email(to: str, subject: str = "Hi") -> str:
            """Send an email."""
            self.calls.append(("send_email", to))
            return f"sent to {to}"

        @checker.guard(name="refund")
        def issue_refund(order_id: str, amount: float) -> str:
            self.calls.append(("refund", amount))
            return "refunded"

        return checker, send_email, issue_refund

    def test_allowed_call_runs(self):
        checker, send_email, _ = self.make()
        with checker.context(sender="a@x.com"):
            self.assertEqual(send_email("a@x.com"), "sent to a@x.com")
        self.assertEqual(self.calls, [("send_email", "a@x.com")])

    def test_blocked_call_never_runs(self):
        checker, send_email, _ = self.make()
        with checker.context(sender="a@x.com"):
            result = send_email(to="evil@x.com")
        self.assertTrue(result.startswith("BLOCKED"))
        self.assertEqual(self.calls, [])

    def test_raise_mode(self):
        checker, send_email, _ = self.make(on_block="raise")
        with checker.context(sender="a@x.com"), self.assertRaises(Blocked):
            send_email("evil@x.com")

    def test_missing_context_fails_closed(self):
        _, send_email, _ = self.make()
        self.assertIn("policy error", send_email("a@x.com"))
        self.assertEqual(self.calls, [])

    def test_ask_goes_to_the_approver(self):
        seen = []
        _, _, refund = self.make(approver=lambda intent, reason: seen.append(reason) or True)
        self.assertEqual(refund("o1", 450), "refunded")
        self.assertEqual(seen, ["big refund"])

        _, _, refund = self.make(approver=lambda intent, reason: False)
        self.assertIn("a human declined", refund("o1", 450))

        _, _, refund = self.make()
        self.assertIn("no approver", refund("o1", 450))

    def test_signature_and_docs_are_kept(self):
        _, send_email, _ = self.make()
        self.assertEqual(list(inspect.signature(send_email).parameters), ["to", "subject"])
        self.assertEqual(send_email.__doc__, "Send an email.")
        self.assertEqual(send_email.__name__, "send_email")

    def test_async_tools(self):
        checker = Checker(POLICY, audit_log=None)

        @checker.guard
        async def send_email(to: str) -> str:
            return f"sent to {to}"

        async def run():
            with checker.context(sender="a@x.com"):
                return await send_email("a@x.com"), await send_email("evil@x.com")

        ok, blocked = asyncio.run(run())
        self.assertEqual(ok, "sent to a@x.com")
        self.assertTrue(blocked.startswith("BLOCKED"))

    def test_contexts_do_not_leak_between_tasks(self):
        checker = Checker(POLICY, audit_log=None)

        @checker.guard
        async def send_email(to: str) -> str:
            await asyncio.sleep(0.01)
            return "sent"

        async def as_user(sender, to):
            with checker.context(sender=sender):
                return await send_email(to)

        async def run():
            return await asyncio.gather(as_user("a@x.com", "a@x.com"), as_user("b@x.com", "a@x.com"))

        self.assertEqual(asyncio.run(run())[0], "sent")
        self.assertTrue(asyncio.run(run())[1].startswith("BLOCKED"))

    def test_excluded_params_are_ignored_by_policy(self):
        checker = Checker({"rules": [{"tool": "t", "match": {"x": {"equals": 1}}, "decision": "allow"}]}, audit_log=None)

        @checker.guard(exclude=["ctx"])
        def t(ctx, x: int) -> str:
            return "ran"

        self.assertEqual(t(object(), 1), "ran")

    def test_check_without_running(self):
        checker, _, _ = self.make()
        self.assertTrue(checker.check("send_email", {"to": "a@x.com"}, {"sender": "a@x.com"}).allowed)
        self.assertFalse(checker.check("rm_rf", {}).allowed)

    def test_audit_log(self):
        checker, send_email, _ = self.make()
        with checker.context(sender="a@x.com"):
            send_email("a@x.com")
            send_email("evil@x.com")
        events = [json.loads(line)["event"] for line in self.log.read_text().splitlines()]
        self.assertEqual(events, ["proposed", "decision", "executed", "proposed", "decision"])
        self.assertTrue(checker.recorder.verify())

        lines = self.log.read_text().splitlines()
        tampered = json.loads(lines[4])
        tampered["data"]["allowed"] = True
        lines[4] = json.dumps(tampered)
        self.log.write_text("\n".join(lines) + "\n")
        self.assertFalse(checker.recorder.verify())


class TokenTest(unittest.TestCase):
    def setUp(self):
        self.gate = Gatekeeper(Policy(default="allow"), b"secret")
        self.doer = Doer(b"secret")
        self.intent = Intent("refund", {"amount": 20})

    def test_valid_token_once(self):
        token = self.gate.review(self.intent).token
        self.assertEqual(self.doer.run(self.intent, token, lambda: "ok"), "ok")
        with self.assertRaises(NotApproved):
            self.doer.run(self.intent, token, lambda: "again")

    def test_token_is_bound_to_the_exact_action(self):
        token = self.gate.review(self.intent).token
        with self.assertRaises(NotApproved):
            self.doer.run(Intent("refund", {"amount": 9000}), token, lambda: "ok")

    def test_forged_and_missing_tokens(self):
        forged = Gatekeeper(Policy(default="allow"), b"other").review(self.intent).token
        for token in (None, "", forged):
            with self.subTest(token=token), self.assertRaises(NotApproved):
                self.doer.run(self.intent, token, lambda: "ok")


if __name__ == "__main__":
    unittest.main()
