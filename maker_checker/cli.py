"""Command line: `maker-checker check | serve | verify`."""

from __future__ import annotations

import argparse
import json
import sys

from . import adapters
from .intents import Verdict
from .policy import Policy
from .recorder import Recorder, verify_log


def _parse_context(pairs: list[str]) -> dict:
    context = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        context[key] = value
    return context


def cmd_check(args) -> int:
    """Read one tool call as JSON on stdin, print the decision as JSON.
    Anything unexpected (bad policy, bad input) fails closed as "deny"."""
    try:
        policy = Policy.from_file(args.policy)
        intent, context = adapters.parse(args.format, json.loads(sys.stdin.read() or "{}"))
        context.update(_parse_context(args.context))
        verdict = adapters.evaluate(policy, intent, context)
    except Exception as error:
        intent, verdict = None, Verdict("deny", f"maker-checker couldn't evaluate this call: {error}")

    if args.log and intent is not None:
        recorder = Recorder(args.log)
        recorder.record("proposed", tool=intent.tool, args=intent.args, via=args.format)
        recorder.record("decision", tool=intent.tool, effect=verdict.effect, reason=verdict.reason)

    output = adapters.render(args.format, verdict)
    if output is not None:
        print(json.dumps(output))
    return 0


def cmd_serve(args) -> int:
    from .server import make_server

    server = make_server(
        Policy.from_file(args.policy),
        host=args.host,
        port=args.port,
        recorder=Recorder(args.log) if args.log else None,
    )
    print(f"maker-checker listening on http://{args.host}:{args.port}  (POST /check)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_verify(args) -> int:
    if verify_log(args.log):
        print(f"✓ {args.log}: chain intact")
        return 0
    print(f"✗ {args.log}: chain broken (an entry was edited, removed or reordered)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maker-checker", description="Policy gate for AI agent tool calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="decide one tool call read from stdin (for hooks and scripts)")
    check.add_argument("--policy", required=True, help="path to a .toml policy")
    check.add_argument("--format", default="generic", choices=adapters.FORMATS)
    check.add_argument("--log", help="append the decision to this audit log")
    check.add_argument("--context", action="append", default=[], metavar="KEY=VALUE", help="trusted context")
    check.set_defaults(func=cmd_check)

    serve = sub.add_parser("serve", help="run the HTTP gate")
    serve.add_argument("--policy", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--log", help="audit log path")
    serve.set_defaults(func=cmd_serve)

    verify = sub.add_parser("verify", help="check an audit log hasn't been tampered with")
    verify.add_argument("log")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
