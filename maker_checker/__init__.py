"""maker-checker: a framework-agnostic policy gate for AI agent tool calls.

The LLM proposes, plain code approves (or asks a human), only approved calls
run, and a tamper-evident log records every step.
"""

from .approvers import cli_approver, deny_all
from .checker import Blocked, Checker
from .doer import Doer, NotApproved
from .gatekeeper import Gatekeeper
from .intents import Decision, Intent, Verdict
from .policy import Policy, Rule
from .recorder import Recorder, verify_log

__version__ = "0.2.0"

__all__ = [
    "Blocked",
    "Checker",
    "Decision",
    "Doer",
    "Gatekeeper",
    "Intent",
    "NotApproved",
    "Policy",
    "Recorder",
    "Rule",
    "Verdict",
    "cli_approver",
    "deny_all",
    "verify_log",
]
