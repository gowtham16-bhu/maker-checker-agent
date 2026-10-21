"""Your rules, as data or plain code. No LLM is involved, so a clever prompt
can't talk its way past them.

A policy is an ordered list of rules. The first rule that matches a tool call
decides it: "allow", "deny" or "ask" (a human approves). If no rule matches,
`default` applies.

    default = "deny"

    [[rules]]
    tool = "issue_refund"
    match = { amount = { max = 100 } }
    decision = "allow"

    [[rules]]
    tool = "issue_refund"
    decision = "ask"
    reason = "refunds over $100 need a human"

`tool` is a name, a glob ("mcp__github__*") or a list of them.

Conditions in `match` (all must hold; several can apply to the same argument):

    equals, one_of        exact value / one of a list
    regex, not_regex      re.search on a string argument
    min, max              numeric bounds
    within, not_within    path is (not) inside a folder; symlinks are resolved

A value written as "$context.<key>" is filled from trusted context you pass in,
such as the real sender of an email or the project folder. Never from the LLM.
"""

from __future__ import annotations

import fnmatch
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .intents import Effect, Intent, Verdict

EFFECTS = ("allow", "deny", "ask")
CONDITIONS = ("equals", "one_of", "regex", "not_regex", "min", "max", "within", "not_within")


def _resolve(value: Any, context: dict) -> Any:
    if isinstance(value, str) and value.startswith("$context."):
        key = value[len("$context."):]
        if key not in context:
            raise KeyError(f"policy needs $context.{key}, but it wasn't provided")
        return context[key]
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _within(value: Any, folder: Any, context: dict) -> bool:
    if not isinstance(value, str) or not folder:
        return False
    root = Path(str(folder)).expanduser().resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(context.get("cwd") or os.getcwd()) / path
    path = path.resolve()
    return path == root or root in path.parents


def _check(op: str, value: Any, expected: Any, context: dict) -> bool:
    if op == "equals":
        return value == expected
    if op == "one_of":
        return value in expected
    if op == "regex":
        return isinstance(value, str) and re.search(expected, value) is not None
    if op == "not_regex":
        return isinstance(value, str) and re.search(expected, value) is None
    if op == "min":
        return _is_number(value) and value >= expected
    if op == "max":
        return _is_number(value) and value <= expected
    if op == "within":
        return _within(value, expected, context)
    if op == "not_within":
        return isinstance(value, str) and not _within(value, expected, context)
    raise ValueError(f"unknown condition '{op}'")


@dataclass(frozen=True)
class Rule:
    tools: tuple[str, ...]
    decision: Effect
    match: dict
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        decision = data.get("decision")
        if decision not in EFFECTS:
            raise ValueError(f"rule decision must be one of {EFFECTS}, got {decision!r}")
        for arg, conditions in data.get("match", {}).items():
            unknown = set(conditions) - set(CONDITIONS)
            if unknown:
                raise ValueError(f"unknown condition(s) {sorted(unknown)} on '{arg}'")
        tools = data.get("tool", "*")
        return cls(
            tools=(tools,) if isinstance(tools, str) else tuple(tools),
            decision=decision,
            match=data.get("match", {}),
            reason=data.get("reason", ""),
        )

    def applies(self, intent: Intent, context: dict) -> bool:
        if not any(fnmatch.fnmatchcase(intent.tool, pattern) for pattern in self.tools):
            return False
        for arg, conditions in self.match.items():
            if arg not in intent.args:
                return False
            for op, expected in conditions.items():
                if not _check(op, intent.args[arg], _resolve(expected, context), context):
                    return False
        return True


# A code rule returns a Verdict to decide, or None to pass to the next rule.
CodeRule = Callable[[Intent, dict], "Verdict | None"]


class Policy:
    def __init__(self, rules: list[Rule | CodeRule] | None = None, default: Effect = "deny"):
        if default not in EFFECTS:
            raise ValueError(f"default must be one of {EFFECTS}")
        self.rules = list(rules or [])
        self.default = default

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        return cls([Rule.from_dict(r) for r in data.get("rules", [])], data.get("default", "deny"))

    @classmethod
    def from_toml(cls, text: str) -> "Policy":
        return cls.from_dict(tomllib.loads(text))

    @classmethod
    def from_file(cls, path: str | Path) -> "Policy":
        return cls.from_toml(Path(path).read_text())

    @classmethod
    def load(cls, source: "Policy | dict | str | Path") -> "Policy":
        """Accept a Policy, a dict, or a path to a .toml file."""
        if isinstance(source, Policy):
            return source
        if isinstance(source, dict):
            return cls.from_dict(source)
        return cls.from_file(source)

    def evaluate(self, intent: Intent, context: dict | None = None) -> Verdict:
        context = context or {}
        for number, rule in enumerate(self.rules, start=1):
            if isinstance(rule, Rule):
                if rule.applies(intent, context):
                    return Verdict(rule.decision, rule.reason or f"rule {number} says {rule.decision}")
            else:
                verdict = rule(intent, context)
                if verdict is not None:
                    return verdict
        return Verdict(self.default, f"no rule matched; default is {self.default}")
