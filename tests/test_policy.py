import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maker_checker import Intent, Policy, Verdict  # noqa: E402

TOML = """
default = "deny"

[[rules]]
tool = "issue_refund"
match = { amount = { max = 100 } }
decision = "allow"

[[rules]]
tool = "issue_refund"
decision = "ask"
reason = "big refund"

[[rules]]
tool = "send_email"
match = { to = { equals = "$context.sender" } }
decision = "allow"

[[rules]]
tool = "mcp__github__*"
decision = "ask"

[[rules]]
tool = ["Read", "Write"]
match = { file_path = { within = "$context.cwd" } }
decision = "allow"
"""


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = Policy.from_toml(TOML)

    def effect(self, tool, args, **context):
        return self.policy.evaluate(Intent(tool, args), context).effect

    def test_first_match_wins(self):
        self.assertEqual(self.effect("issue_refund", {"amount": 40}), "allow")
        self.assertEqual(self.effect("issue_refund", {"amount": 450}), "ask")

    def test_reason_comes_from_rule(self):
        verdict = self.policy.evaluate(Intent("issue_refund", {"amount": 450}))
        self.assertEqual(verdict.reason, "big refund")

    def test_default_applies(self):
        self.assertEqual(self.effect("delete_everything", {}), "deny")

    def test_context_values(self):
        self.assertEqual(self.effect("send_email", {"to": "a@x.com"}, sender="a@x.com"), "allow")
        self.assertEqual(self.effect("send_email", {"to": "evil@x.com"}, sender="a@x.com"), "deny")

    def test_missing_context_raises(self):
        with self.assertRaises(KeyError):
            self.effect("send_email", {"to": "a@x.com"})

    def test_glob_tool_names(self):
        self.assertEqual(self.effect("mcp__github__create_issue", {}), "ask")

    def test_numbers_only_for_min_max(self):
        self.assertEqual(self.effect("issue_refund", {"amount": "40"}), "ask")
        self.assertEqual(self.effect("issue_refund", {"amount": True}), "ask")

    def test_within_folder(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as outside:
            self.assertEqual(self.effect("Read", {"file_path": "src/app.py"}, cwd=project), "allow")
            self.assertEqual(self.effect("Read", {"file_path": f"{project}/a.txt"}, cwd=project), "allow")
            self.assertEqual(self.effect("Read", {"file_path": "../../etc/passwd"}, cwd=project), "deny")
            self.assertEqual(self.effect("Write", {"file_path": f"{outside}/x"}, cwd=project), "deny")

    def test_within_follows_symlinks(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(project, "sneaky"))
            self.assertEqual(self.effect("Write", {"file_path": "sneaky/x"}, cwd=project), "deny")

    def test_regex_and_not_regex_together(self):
        policy = Policy.from_dict({"rules": [{
            "tool": "Bash",
            "match": {"command": {"regex": r"^ls\b", "not_regex": r"[;&|]"}},
            "decision": "allow",
        }]})
        self.assertEqual(policy.evaluate(Intent("Bash", {"command": "ls -la"})).effect, "allow")
        self.assertEqual(policy.evaluate(Intent("Bash", {"command": "ls; rm -rf /"})).effect, "deny")

    def test_code_rules(self):
        def no_weekend_refunds(intent, context):
            if intent.tool == "issue_refund" and context.get("weekday") in ("Sat", "Sun"):
                return Verdict("deny", "no refunds at weekends")
            return None

        policy = Policy([no_weekend_refunds], default="allow")
        self.assertEqual(policy.evaluate(Intent("issue_refund", {}), {"weekday": "Sun"}).effect, "deny")
        self.assertEqual(policy.evaluate(Intent("issue_refund", {}), {"weekday": "Mon"}).effect, "allow")

    def test_bad_rules_rejected(self):
        with self.assertRaises(ValueError):
            Policy.from_dict({"rules": [{"tool": "x", "decision": "maybe"}]})
        with self.assertRaises(ValueError):
            Policy.from_dict({"rules": [{"tool": "x", "decision": "allow", "match": {"a": {"bigger": 1}}}]})

    def test_example_policies_load(self):
        for path in (Path(__file__).parent.parent / "examples" / "policies").glob("*.toml"):
            with self.subTest(policy=path.name):
                Policy.from_file(path)


if __name__ == "__main__":
    unittest.main()
