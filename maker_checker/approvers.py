"""Ready-made approvers for "ask" decisions. An approver is any function
`(intent, reason) -> bool`, so you can plug in Slack, email, a web UI, etc."""

from __future__ import annotations

from .intents import Intent


def cli_approver(intent: Intent, reason: str) -> bool:
    """Ask in the terminal."""
    print(f"\n🚦 Approval needed: {intent}\n   Why: {reason}", flush=True)
    try:
        answer = input("   Allow it? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def deny_all(intent: Intent, reason: str) -> bool:
    """For unattended runs: every "ask" becomes "no"."""
    return False
