"""Translate between maker-checker and the JSON that other agents speak, so
the same policy can guard agents you don't write in Python.

    generic      {"tool": ..., "args": {...}, "context": {...}}
                 -> {"decision": "allow|deny|ask", "reason": ...}
    claude-code  Claude Code PreToolUse hook
    codex        OpenAI Codex PreToolUse hook (can't "ask": ask becomes deny)
    cursor       Cursor preToolUse hook (doesn't enforce "ask": ask becomes deny)
"""

from __future__ import annotations

import os

from .intents import Intent, Verdict
from .policy import Policy

FORMATS = ("generic", "claude-code", "codex", "cursor")


def parse(fmt: str, payload: dict) -> tuple[Intent, dict]:
    """Return the proposed call and the trusted context for it."""
    if fmt == "generic":
        return Intent(payload["tool"], payload.get("args") or {}), payload.get("context") or {}

    roots = payload.get("workspace_roots") or []
    context = {
        "cwd": payload.get("cwd") or (roots[0] if roots else os.getcwd()),
        "agent": fmt,
    }
    for key in ("session_id", "conversation_id", "user_email"):
        if payload.get(key):
            context[key] = payload[key]
    return Intent(payload.get("tool_name", ""), payload.get("tool_input") or {}), context


def evaluate(policy: Policy, intent: Intent, context: dict) -> Verdict:
    """Like policy.evaluate, but a broken rule fails closed."""
    try:
        return policy.evaluate(intent, context)
    except Exception as error:
        return Verdict("deny", f"policy error: {error}")


def render(fmt: str, verdict: Verdict) -> dict | None:
    """The JSON to print on stdout. None means print nothing (let it run)."""
    effect, reason = verdict.effect, verdict.reason
    message = f"maker-checker: {reason}"

    if fmt == "generic":
        return {"decision": effect, "reason": reason}

    if fmt == "claude-code":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": effect,
                "permissionDecisionReason": message,
            }
        }

    if fmt == "codex":
        if effect == "allow":
            return None
        if effect == "ask":
            message = f"maker-checker: needs human approval, which Codex hooks can't request ({reason})"
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            }
        }

    if fmt == "cursor":
        if effect == "allow":
            return {"permission": "allow"}
        if effect == "ask":
            message = f"maker-checker: needs human approval, which Cursor's preToolUse can't request ({reason})"
        return {"permission": "deny", "user_message": message, "agent_message": message}

    raise ValueError(f"unknown format '{fmt}', expected one of {FORMATS}")
