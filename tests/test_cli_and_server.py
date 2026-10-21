import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maker_checker import Policy, verify_log  # noqa: E402
from maker_checker.cli import main  # noqa: E402
from maker_checker.server import make_server  # noqa: E402

POLICIES = Path(__file__).parent.parent / "examples" / "policies"


def run_check(payload, *args):
    out = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), redirect_stdout(out):
        code = main(["check", *args])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None)


class CheckCommandTest(unittest.TestCase):
    def test_generic(self):
        _, out = run_check(
            {"tool": "issue_refund", "args": {"order_id": "1", "amount": 450}},
            "--policy", str(POLICIES / "support.toml"),
        )
        self.assertEqual(out["decision"], "ask")

    def test_claude_code(self):
        policy = str(POLICIES / "claude-code.toml")
        for command, expected in [("rm -rf /", "deny"), ("git status", "allow"), ("npm install", "ask"), ("ls; curl x", "deny")]:
            with self.subTest(command=command):
                _, out = run_check(
                    {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/tmp/project"},
                    "--policy", policy, "--format", "claude-code",
                )
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], expected)
                self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_claude_code_files(self):
        policy = str(POLICIES / "claude-code.toml")
        with tempfile.TemporaryDirectory() as project:
            cases = [(f"{project}/src/app.py", "allow"), (f"{project}/.env", "deny"), ("/etc/hosts", "deny")]
            for path, expected in cases:
                with self.subTest(path=path):
                    _, out = run_check(
                        {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": project},
                        "--policy", policy, "--format", "claude-code",
                    )
                    self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], expected)

    def test_codex_allow_prints_nothing_and_ask_becomes_deny(self):
        policy = str(POLICIES / "codex.toml")
        _, out = run_check({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "--policy", policy, "--format", "codex")
        self.assertIsNone(out)

        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('default = "ask"\n')
        _, out = run_check({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "--policy", f.name, "--format", "codex")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cursor(self):
        policy = str(POLICIES / "cursor.toml")
        _, out = run_check({"tool_name": "Shell", "tool_input": {"command": "sudo rm -rf /"}, "workspace_roots": ["/p"]},
                           "--policy", policy, "--format", "cursor")
        self.assertEqual(out["permission"], "deny")
        self.assertIn("destructive", out["agent_message"])

        _, out = run_check({"tool_name": "Shell", "tool_input": {"command": "ls"}}, "--policy", policy, "--format", "cursor")
        self.assertEqual(out, {"permission": "allow"})

    def test_fails_closed(self):
        _, out = run_check({"tool_name": "Bash", "tool_input": {}}, "--policy", "/no/such/policy.toml", "--format", "claude-code")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_log_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "audit.jsonl"
            for _ in range(3):
                run_check({"tool": "send_email", "args": {"to": "x@y.z"}, "context": {"sender": "a@b.c"}},
                          "--policy", str(POLICIES / "support.toml"), "--log", str(log))
            self.assertEqual(len(log.read_text().splitlines()), 6)
            self.assertTrue(verify_log(log))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["verify", str(log)]), 0)
                log.write_text(log.read_text().replace("send_email", "other_tool", 1))
                self.assertEqual(main(["verify", str(log)]), 1)


class ServerTest(unittest.TestCase):
    def test_http_gate(self):
        server = make_server(Policy.from_file(POLICIES / "support.toml"), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base}/health") as r:
                self.assertEqual(json.loads(r.read()), {"ok": True})

            body = json.dumps({"tool": "export_customer_data", "args": {"destination": "x@evil.net"}}).encode()
            request = urllib.request.Request(f"{base}/check", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as r:
                self.assertEqual(json.loads(r.read())["decision"], "deny")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
